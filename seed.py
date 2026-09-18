from app import create_app, db
from app.models import User, Ticket, TicketStatusHistory

app = create_app()

with app.app_context():
    db.drop_all()
    db.create_all()

    # Seed Admin User
    
# In seed.py, update the admin creation line:
    admin = User(name="System Admin", email="admin@smartdesk.local", role="admin")
    admin.set_password("Admin@123")
    db.session.add(admin)
    db.session.commit()

    # Seed Sample Ticket
    sample_ticket = Ticket(
        reference_no="TKT-00001",
        customer_name="Alice Smith",
        customer_email="alice@example.com",
        subject="Payment debited twice",
        description="I was charged two times for the annual billing cycle.",
        status="Open",
        category="Billing",
        priority="High",
        ai_summary="Customer reports duplicate charges for annual subscription."
    )
    db.session.add(sample_ticket)
    db.session.commit()

    history = TicketStatusHistory(
        ticket_id=sample_ticket.id,
        previous_status="Open",
        new_status="Open",
        remark="Ticket created by customer.",
        changed_by_id=None
    )
    db.session.add(history)
    db.session.commit()

    print("Database seeded successfully:")
    print("Email: admin@smartdesk.local | Password: Admin@123")