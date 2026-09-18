import re
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app import db
from app.models import User, Ticket, TicketStatusHistory
from app.services.ai_service import classify_ticket

api_bp = Blueprint('api', __name__)

EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(identity=user.id)
    return jsonify({"access_token": token, "token_type": "Bearer"}), 200

@api_bp.route('/tickets', methods=['POST'])
def create_ticket():
    data = request.get_json() or {}
    errors = {}

    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    subject = data.get('subject', '').strip()
    description = data.get('description', '').strip()

    if not name:
        errors['name'] = "Customer name is required."
    if not email or not re.match(EMAIL_REGEX, email):
        errors['email'] = "A valid email address is required."
    if not subject:
        errors['subject'] = "Subject is required."
    if not description:
        errors['description'] = "Description is required."

    if errors:
        return jsonify({"errors": errors}), 422

    # Step 1: Run AI Classification
    ai_result = classify_ticket(subject, description)

    # Step 2: Persist Ticket to reserve ID & derive reference number
    ticket = Ticket(
        reference_no="TEMP",
        customer_name=name,
        customer_email=email,
        subject=subject,
        description=description,
        status='Open',
        category=ai_result['category'],
        priority=ai_result['priority'],
        ai_summary=ai_result['ai_summary']
    )
    db.session.add(ticket)
    db.session.flush()

    ticket.reference_no = Ticket.generate_reference_no(ticket.id)
    db.session.commit()

    return jsonify({
        "message": "Ticket created successfully",
        "ticket": {
            "id": ticket.id,
            "reference_no": ticket.reference_no,
            "category": ticket.category,
            "priority": ticket.priority,
            "ai_summary": ticket.ai_summary,
            "status": ticket.status
        }
    }), 201

@api_bp.route('/tickets', methods=['GET'])
@jwt_required()
def list_tickets():
    status = request.args.get('status')
    category = request.args.get('category')
    priority = request.args.get('priority')
    search = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    query = Ticket.query

    if status:
        query = query.filter_by(status=status)
    if category:
        query = query.filter_by(category=category)
    if priority:
        query = query.filter_by(priority=priority)
    if search:
        search_fmt = f"%{search}%"
        query = query.filter(
            db.or_(
                Ticket.reference_no.ilike(search_fmt),
                Ticket.subject.ilike(search_fmt),
                Ticket.customer_email.ilike(search_fmt)
            )
        )

    paginated = query.order_by(Ticket.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "total": paginated.total,
        "page": paginated.page,
        "pages": paginated.pages,
        "tickets": [{
            "id": t.id,
            "reference_no": t.reference_no,
            "subject": t.subject,
            "customer_email": t.customer_email,
            "status": t.status,
            "category": t.category,
            "priority": t.priority,
            "created_at": t.created_at.isoformat()
        } for t in paginated.items]
    }), 200

@api_bp.route('/tickets/<int:ticket_id>', methods=['GET'])
@jwt_required()
def get_ticket(ticket_id):
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404

    history_list = [{
        "previous_status": h.previous_status,
        "new_status": h.new_status,
        "remark": h.remark,
        "changed_by": h.user.name if h.user else "System",
        "created_at": h.created_at.isoformat()
    } for h in ticket.history]

    return jsonify({
        "id": ticket.id,
        "reference_no": ticket.reference_no,
        "customer_name": ticket.customer_name,
        "customer_email": ticket.customer_email,
        "subject": ticket.subject,
        "description": ticket.description,
        "status": ticket.status,
        "category": ticket.category,
        "priority": ticket.priority,
        "ai_summary": ticket.ai_summary,
        "history": history_list
    }), 200

@api_bp.route('/tickets/<int:ticket_id>/status', methods=['PATCH'])
@jwt_required()
def update_ticket_status(ticket_id):
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404

    data = request.get_json() or {}
    new_status = data.get('status')
    remark = data.get('remark', '').strip()

    valid_statuses = {'Open', 'In Progress', 'Resolved', 'Closed'}
    if new_status not in valid_statuses:
        return jsonify({"error": f"Invalid status. Must be one of {list(valid_statuses)}"}), 422
    if not remark:
        return jsonify({"error": "A remark is required for status updates."}), 422

    user_id = get_jwt_identity()

    # Track status change history
    history_entry = TicketStatusHistory(
        ticket_id=ticket.id,
        previous_status=ticket.status,
        new_status=new_status,
        remark=remark,
        changed_by_id=user_id
    )
    ticket.status = new_status

    db.session.add(history_entry)
    db.session.commit()

    return jsonify({"message": "Status updated successfully", "current_status": ticket.status}), 200