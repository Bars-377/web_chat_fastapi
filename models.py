import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime
from passlib.context import CryptContext

# Определение моделей
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users_web"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    def verify_password(self, password: str):
        return pwd_context.verify(password, self.hashed_password)

    def set_password(self, password: str):
        self.hashed_password = pwd_context.hash(password)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users_web.id"))
    receiver_id = Column(Integer, ForeignKey("users_web.id"))
    content = Column(String)
    username = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Подключение к базе данных
DATABASE_URL = "mysql+asyncmy://root:enigma1418@localhost/mdtomskbot"

# Создание движка
engine = create_async_engine(DATABASE_URL, echo=True, future=True)

# Создание асинхронной сессии
async_session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

# Асинхронная функция для создания таблицы
async def init_db():
    print("Инициализация базы данных...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("База данных инициализирована.")

# Функция для получения сессии базы данных
async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session

# Основная асинхронная функция
async def main():
    await init_db()
    await engine.dispose()

# Запуск основной функции
if __name__ == "__main__":
    asyncio.run(main())
