import asyncio

from sqlalchemy import select

from examples.auth.database import AsyncSessionLocal
from examples.auth.models import User


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == "user"))
        user = result.unique().scalar_one_or_none()

        if user is None:
            user = User(
                username="user",
                role="admin",
                is_active=True,
            )
            user.set_password("test1234")
            db.add(user)
            print("Created new admin user: user / test1234")
        else:
            user.set_password("test1234")
            print("Updated password for user -> test1234")

        await db.commit()
        print("Done, please restart backend and login again.")


if __name__ == "__main__":
    asyncio.run(main())