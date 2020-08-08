from flask_login import UserMixin

from db import get_db

class User(UserMixin):
    def __init__(self, id_, name, email, rollno):
        self.id = id_
        self.name = name
        self.email = email
        self.rollno = rollno

    @staticmethod
    def get(user_id):
        db = get_db()
        user = db.execute(
            "SELECT * FROM user WHERE id = ?", (user_id,)
        ).fetchone()
        if not user:
            return None

        user = User(
            user[0], user[1], user[2], user[3]
        )
        return user

    @staticmethod
    def create(id_, name, email, rollno):
        db = get_db()
        db.execute(
            "INSERT INTO user (id, name, email, rollno) "
            "VALUES (?, ?, ?, ?)",
            (id_, name, email, rollno),
        )
        db.commit()
