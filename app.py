import os
from app import create_app, db
from app.models import AppUser, Complex, Category, Service, Field, Timeslot, Subscription

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'AppUser': AppUser,
        'Complex': Complex,
        'Category': Category,
        'Service': Service,
        'Field': Field,
        'Timeslot': Timeslot,
        'Subscription': Subscription
    }

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
