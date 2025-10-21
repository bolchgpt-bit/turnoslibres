from app import create_app, db
from app.models import AppUser, UserComplex


def reset_and_create_superadmin(email: str, password: str) -> None:
    """Deletes all users and user-complex links, then creates a superadmin.

    Args:
        email: Email for the new superadmin.
        password: Plain-text password for the new superadmin.
    """
    # Remove associations first to avoid FK issues
    db.session.query(UserComplex).delete(synchronize_session=False)
    # Remove all users
    db.session.query(AppUser).delete(synchronize_session=False)

    # Create requested superadmin
    admin = AppUser(email=email.lower(), is_superadmin=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    print("All users deleted and superadmin created:")
    print(f"  email: {email}")


def main():
    app = create_app()
    with app.app_context():
        reset_and_create_superadmin(
            email="superadmin@turnoslibres.com",
            password="Lokoleo33",
        )


if __name__ == "__main__":
    main()

