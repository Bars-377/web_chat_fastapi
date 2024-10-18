from fastapi import FastAPI, APIRouter, Depends, HTTPException, WebSocket, Body, WebSocketDisconnect, Request, Response
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import User, Message, get_db
import os
from jose import jwt, JWTError
from passlib.context import CryptContext
import logging
import json

# Конфигурация логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

# Конфигурация FastAPI
app = FastAPI()
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Для работы с паролями
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

import configparser
# Загрузка конфигурации
config = configparser.ConfigParser()
config.read('config.ini')

# Получение значений из конфигурационного файла
SECRET_KEY = config['settings']['SECRET_KEY']
ALGORITHM = config['settings']['ALGORITHM']
ACCESS_TOKEN_EXPIRE_MINUTES = int(config['settings']['ACCESS_TOKEN_EXPIRE_MINUTES'])

from fastapi.staticfiles import StaticFiles
# Подключаем статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

# Обработчик корневого URL, возвращающий HTML файл
@app.get("/")
async def read_root(request: Request):
    access_token = request.cookies.get("access_token")
    logger.info("Access Token: %s", access_token)  # Логгируем значение токена
    if access_token:
        try:
            payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
            return FileResponse(os.path.join("templates", "index.html"))  # Отправляем index.html
        except JWTError:
            logger.error("Invalid token, redirecting to auth.html")
            return RedirectResponse(url="/auth.html")  # Если токен недействителен, перенаправляем на авторизацию
    return RedirectResponse(url="/auth.html")  # Перенаправляем на авторизацию, если токена нет

# Добавление маршрутов для новых страниц
@app.get("/reg.html", response_class=FileResponse)
async def registration_page():
    return FileResponse(os.path.join("templates", "reg.html"))

@app.get("/auth.html", response_class=FileResponse)
async def authorization_page():
    return FileResponse(os.path.join("templates", "auth.html"))

# Регистрация пользователя
@router.post("/register/")
async def register_user(
    username: str = Body(...),
    email: str = Body(...),
    password: str = Body(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        existing_user = await db.execute(select(User).filter(User.username == username))
        if existing_user.scalars().first():
            logger.error("Username already registered: %s", username)
            raise HTTPException(status_code=400, detail="Username already registered")

        existing_email = await db.execute(select(User).filter(User.email == email))
        if existing_email.scalars().first():
            logger.error("Email already registered: %s", email)
            raise HTTPException(status_code=400, detail="Email already registered")

        user = User(username=username, email=email)
        user.set_password(password)
        db.add(user)
        await db.commit()  # Коммит изменений

        # Логин после регистрации
        token_data = {"sub": username}
        access_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

        # Установка куки с токеном
        response = JSONResponse(status_code=201, content={"message": "Пользователь создан", "user_id": user.id})
        response.set_cookie(key="access_token", value=access_token, httponly=True)

        return response

    except Exception as e:
        await db.rollback()  # Откат при ошибке
        logger.error("Error occurred during user registration: %s", str(e))  # Логгирование ошибки
        if str(e) == '400: Username already registered':
            raise HTTPException(status_code=500, detail="400: Username already registered")
        elif str(e) == '400: Email already registered':
            raise HTTPException(status_code=500, detail="400: Email already registered")
        else:
            raise HTTPException(status_code=500, detail="Internal Server Error")

# Логин пользователя и получение JWT токена
@router.post("/token/")
async def login_user(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    async with db.begin():  # Контекстный менеджер автоматически начнет и завершит транзакцию
        try:

            result = await db.execute(select(User).filter(User.username == form_data.username))
            user = result.scalars().first()

            if not user:
                logger.error("User not found: %s", form_data.username)
                raise HTTPException(status_code=400, detail="Invalid username or password")

            if not user.verify_password(form_data.password):
                logger.error("Invalid password for user: %s", form_data.username)
                raise HTTPException(status_code=400, detail="Invalid username or password")

            token_data = {"sub": user.username}
            access_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

            # Установка куки с токеном
            response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
            response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False)  # Убедитесь, что secure=False для локального тестирования
            return response

        except Exception as e:
            logger.error("Error occurred during user login: %s", e)
            await db.rollback()  # Откат при ошибке
            raise HTTPException(status_code=500, detail="Internal Server Error")

# Проверка токена
async def get_current_user(token: str = Depends(oauth2_scheme)):

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError as e:
        logger.error("JWT Error: %s", str(e))
        raise credentials_exception
    return username

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()

    try:
        token_data = await websocket.receive_text()
        token_data = json.loads(token_data)
        token = token_data.get("token")

        if not token:
            await websocket.close(code=1008)  # Policy Violation
            return

        current_user = await get_current_user(token)
        if current_user != user_id:
            await websocket.close(code=1008)  # Policy Violation
            return

        async for db in get_db():  # Итерируем по генератору
            try:
                user_result = await db.execute(select(User).filter(User.username == user_id))
                user = user_result.scalars().first()

                if not user:
                    logger.warning(f"User {user_id} not found.")
                    await websocket.close(code=1008)  # Policy Violation
                    return

                user_id_int = user.id
                user_name = user.username

                while True:
                    data = await websocket.receive_text()
                    if data == "close":
                        await websocket.close()  # Закрытие соединения
                        break

                    message = Message(sender_id=user_id_int, receiver_id=user_id_int, username=user_name, content=data)

                    try:
                        db.add(message)
                        await db.commit()

                        await websocket.send_text(f"{user_name}: {data}")
                    except Exception as db_error:
                        logger.error(f"Database error while committing message: {db_error}")
                        if db.is_active:
                            await db.rollback()  # Откат только в случае ошибки
                        await websocket.send_text("Error while sending message. Please try again.")

            except WebSocketDisconnect:
                logger.info(f"Client {user_name} disconnected")

            except Exception as e:
                logger.error(f"Error in websocket endpoint: {e}")
                if db.is_active:
                    await db.rollback()  # Откат только если была активная транзакция
            # finally:
            #     await websocket.close()  # Закрытие соединения
    except RuntimeError as e:
        logger.error(f"Ошибка закрытия WebSocket: {e}")
    except WebSocketDisconnect:
        logger.info(f"User {user_id} disconnected")
    except Exception as e:
        logger.error(f"Error in websocket endpoint: {e}")

# Получение истории сообщений
@router.get("/history/")
async def get_all_messages(db: AsyncSession = Depends(get_db)):
    async with db.begin():  # Контекстный менеджер автоматически начнет и завершит транзакцию
        try:
            result = await db.execute(select(Message))
            messages = result.scalars().all()
            return messages
        except Exception as e:
            logger.error("Error fetching message history: %s", str(e))
            raise HTTPException(status_code=500, detail="Error fetching message history")

# Добавление маршрутизатора в приложение
app.include_router(router)
