import re
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func, or_
from app import db
from app.models import User, Ticket, TicketStatusHistory
from app.services.ai_service import classify_ticket

web_bp = Blueprint('web', __name__)
EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

# --- CONTEXT PROCESSOR FOR ALERTS ---

@web_bp.app_context_processor
def inject_notifications():
    if current_user.is_authenticated and getattr(current_user, 'role', 'customer') == 'admin':
        recent_alerts = Ticket.query.filter(
            Ticket.status.in_(['Open', 'In Progress'])
        ).order_by(Ticket.created_at.desc()).limit(5).all()
        
        unread_count = Ticket.query.filter_by(status='Open').count()
        return {
            'notifications': recent_alerts,
            'notification_count': unread_count
        }
    return {'notifications': [], 'notification_count': 0}

# --- PUBLIC & AUTHENTICATION ROUTES ---

@web_bp.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('web.dashboard' if current_user.role == 'admin' else 'web.customer_portal'))
    return redirect(url_for('web.login'))

@web_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('web.dashboard' if current_user.role == 'admin' else 'web.customer_portal'))

    errors = {}
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not name:
            errors['name'] = "Name is required."
        if not email or not re.match(EMAIL_REGEX, email):
            errors['email'] = "Valid email is required."
        elif User.query.filter_by(email=email).first():
            errors['email'] = "This email is already registered."
        if not password or len(password) < 6:
            errors['password'] = "Password must be at least 6 characters."

        if not errors:
            customer = User(name=name, email=email, role='customer')
            customer.set_password(password)
            db.session.add(customer)
            db.session.commit()
            login_user(customer)
            flash("Account registered successfully!", "success")
            return redirect(url_for('web.customer_portal'))

    return render_template('register.html', errors=errors)

@web_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('web.dashboard' if current_user.role == 'admin' else 'web.customer_portal'))

    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.name}!", "success")
            if getattr(user, 'role', 'customer') == 'admin':
                return redirect(url_for('web.dashboard'))
            return redirect(url_for('web.customer_portal'))
        error = "Invalid email or password."

    return render_template('login.html', error=error)

@web_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('web.login'))

@web_bp.route('/submit', methods=['GET', 'POST'])
def submit_ticket():
    errors = {}
    form_data = {}

    if current_user.is_authenticated:
        form_data['name'] = current_user.name
        form_data['email'] = current_user.email

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        description = request.form.get('description', '').strip()
        form_data = {'name': name, 'email': email, 'subject': subject, 'description': description}

        if not name:
            errors['name'] = "Name is required."
        if not email or not re.match(EMAIL_REGEX, email):
            errors['email'] = "A valid email address is required."
        if not subject:
            errors['subject'] = "Subject is required."
        if not description:
            errors['description'] = "Description is required."

        if not errors:
            ai_data = classify_ticket(subject, description)

            ticket = Ticket(
                reference_no="TEMP",
                customer_name=name,
                customer_email=email,
                subject=subject,
                description=description,
                status='Open',
                category=ai_data['category'],
                priority=ai_data['priority'],
                ai_summary=ai_data['ai_summary']
            )
            db.session.add(ticket)
            db.session.flush()

            ticket.reference_no = Ticket.generate_reference_no(ticket.id)
            
            history = TicketStatusHistory(
                ticket_id=ticket.id,
                previous_status="None",
                new_status="Open",
                remark="Ticket submitted by customer.",
                changed_by_id=current_user.id if current_user.is_authenticated else None
            )
            db.session.add(history)
            db.session.commit()

            return redirect(url_for('web.confirmation', ref=ticket.reference_no))

    return render_template('submit_ticket.html', errors=errors, form=form_data)

@web_bp.route('/confirmation')
def confirmation():
    ref = request.args.get('ref', '')
    return render_template('confirmation.html', reference_no=ref)

# --- ADMIN PANEL ROUTES ---

@web_bp.route('/dashboard')
@login_required
def dashboard():
    if getattr(current_user, 'role', 'customer') != 'admin':
        return redirect(url_for('web.customer_portal'))

    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    status_counts = dict(db.session.query(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status).all())
    category_counts = dict(db.session.query(Ticket.category, func.count(Ticket.id)).group_by(Ticket.category).all())
    priority_counts = dict(db.session.query(Ticket.priority, func.count(Ticket.id)).group_by(Ticket.priority).all())
    
    recent_7_days = db.session.query(func.count(Ticket.id)).filter(Ticket.created_at >= seven_days_ago).scalar() or 0
    total_tickets = db.session.query(func.count(Ticket.id)).scalar() or 0

    return render_template(
        'dashboard.html',
        status_counts=status_counts,
        category_counts=category_counts,
        priority_counts=priority_counts,
        recent_7_days=recent_7_days,
        total_tickets=total_tickets
    )

@web_bp.route('/tickets')
@login_required
def ticket_list():
    if getattr(current_user, 'role', 'customer') != 'admin':
        return redirect(url_for('web.customer_portal'))

    status = request.args.get('status', '').strip()
    category = request.args.get('category', '').strip()
    priority = request.args.get('priority', '').strip()
    search = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    query = Ticket.query
    if status:
        query = query.filter(Ticket.status == status)
    if category:
        query = query.filter(Ticket.category == category)
    if priority:
        query = query.filter(Ticket.priority == priority)
    if search:
        search_fmt = f"%{search}%"
        query = query.filter(
            or_(
                Ticket.reference_no.ilike(search_fmt),
                Ticket.subject.ilike(search_fmt),
                Ticket.customer_email.ilike(search_fmt)
            )
        )

    pagination = query.order_by(Ticket.created_at.desc()).paginate(page=page, per_page=8, error_out=False)

    return render_template(
        'ticket_list.html',
        pagination=pagination,
        search=search,
        status=status,
        category=category,
        priority=priority
    )

@web_bp.route('/tickets/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
def ticket_detail(ticket_id):
    if getattr(current_user, 'role', 'customer') != 'admin':
        return redirect(url_for('web.customer_portal'))

    ticket = Ticket.query.get_or_404(ticket_id)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_status':
            new_status = request.form.get('status')
            remark = request.form.get('remark', '').strip()
            if not remark:
                flash("Remark is required when modifying status.", "danger")
            elif new_status not in {'Open', 'In Progress', 'Resolved', 'Closed'}:
                flash("Invalid status choice.", "danger")
            else:
                history_entry = TicketStatusHistory(
                    ticket_id=ticket.id,
                    previous_status=ticket.status,
                    new_status=new_status,
                    remark=remark,
                    changed_by_id=current_user.id
                )
                ticket.status = new_status
                db.session.add(history_entry)
                db.session.commit()
                flash("Ticket status updated successfully.", "success")

        elif action == 'override_ai':
            new_category = request.form.get('category')
            new_priority = request.form.get('priority')
            if new_category in {'Technical', 'Billing', 'Account', 'General'}:
                ticket.category = new_category
            if new_priority in {'Low', 'Medium', 'High'}:
                ticket.priority = new_priority
            db.session.commit()
            flash("AI classification overridden successfully.", "info")

        return redirect(url_for('web.ticket_detail', ticket_id=ticket.id))

    return render_template('ticket_detail.html', ticket=ticket)

# --- CUSTOMER PORTAL ROUTES ---

@web_bp.route('/portal')
@login_required
def customer_portal():
    if getattr(current_user, 'role', 'customer') == 'admin':
        return redirect(url_for('web.dashboard'))

    user_tickets = Ticket.query.filter_by(customer_email=current_user.email).order_by(Ticket.created_at.desc()).all()
    
    total = len(user_tickets)
    open_count = sum(1 for t in user_tickets if t.status == 'Open')
    progress_count = sum(1 for t in user_tickets if t.status == 'In Progress')
    resolved_count = sum(1 for t in user_tickets if t.status in ['Resolved', 'Closed'])

    return render_template(
        'customer_portal.html',
        tickets=user_tickets[:5],
        total=total,
        open_count=open_count,
        progress_count=progress_count,
        resolved_count=resolved_count
    )

@web_bp.route('/my-tickets')
@login_required
def my_tickets():
    user_tickets = Ticket.query.filter_by(customer_email=current_user.email).order_by(Ticket.created_at.desc()).all()
    return render_template('my_tickets.html', tickets=user_tickets)

@web_bp.route('/my-tickets/<int:ticket_id>')
@login_required
def customer_ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if ticket.customer_email != current_user.email and getattr(current_user, 'role', 'customer') != 'admin':
        flash("Unauthorized ticket access.", "danger")
        return redirect(url_for('web.customer_portal'))

    return render_template('customer_ticket_detail.html', ticket=ticket)