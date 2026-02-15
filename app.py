from flask import session
import os
from datetime import datetime
from flask import Flask, request, redirect, render_template, url_for, send_from_directory, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from functools import wraps
from flask_mail import Mail, Message
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from sqlalchemy import text

# --- Setup ---
BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Initialize Flask ---
app = Flask(__name__)

# --- Flask Configs ---
app.config['SECRET_KEY'] = 'dev-secret-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'aid.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8MB

# --- Mail Config ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'bmahendhar59@gmail.com'
app.config['MAIL_PASSWORD'] = 'YOUR_APP_PASSWORD'
mail = Mail(app)

# --- Twilio Config ---
app.config['TWILIO_ACCOUNT_SID'] = 'AC600926e628bfb15031238b623b4e1ae7'
app.config['TWILIO_AUTH_TOKEN'] = '9313988d78359cb1a192572c53523b4f'
app.config['TWILIO_FROM_NUMBER'] = '+12294598732'
app.config['ADMIN_PHONE'] = '+918197437307'
twilio_client = Client(app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN'])

# --- Database ---
from flask_socketio import SocketIO

db = SQLAlchemy(app)
# --- Socket.IO (realtime) ---
# Prefer eventlet if available, otherwise fall back to threading to avoid crash
try:
    import eventlet  # type: ignore
    eventlet.monkey_patch()
    _async_mode = 'eventlet'
    print('Using eventlet async mode for Socket.IO')
except Exception:
    _async_mode = 'threading'
    print('eventlet not available or failed to initialize; falling back to threading async mode for Socket.IO')

socketio = SocketIO(app, cors_allowed_origins='*', async_mode=_async_mode)

# --- Login Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True)
    password = db.Column(db.String)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    beneficiary_name = db.Column(db.String(100))
    beneficiary_id = db.Column(db.String(50))
    item = db.Column(db.String(200))
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    donor_lat = db.Column(db.Float, nullable=True)
    donor_lon = db.Column(db.Float, nullable=True)
    photo_filename = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pending')
    delivery_status = db.Column(db.String(20), default='Pending')
    current_lat = db.Column(db.Float, nullable=True)
    current_lon = db.Column(db.Float, nullable=True)
    last_updated = db.Column(db.DateTime, nullable=True)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer)
    action = db.Column(db.String)
    actor = db.Column(db.String)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String)

class AidRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(20), nullable=False)
    family_id = db.Column(db.String(50), nullable=True)
    aid_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    emergency_status = db.Column(db.String(50), nullable=True)

# --- Ensure DB and Columns ---
def ensure_db_and_columns():
    db.create_all()
    try:
        res = db.session.execute(text("PRAGMA table_info('transaction')")).fetchall()
        cols = [r[1] for r in res]
        if 'donor_lat' not in cols:
            db.session.execute(text("ALTER TABLE transaction ADD COLUMN donor_lat REAL;"))
        if 'donor_lon' not in cols:
            db.session.execute(text("ALTER TABLE transaction ADD COLUMN donor_lon REAL;"))
        # Ensure emergency_status exists on aid_request table for older DBs
        try:
            res2 = db.session.execute(text("PRAGMA table_info('aid_request')")).fetchall()
            cols2 = [r[1] for r in res2]
            if 'emergency_status' not in cols2:
                db.session.execute(text("ALTER TABLE aid_request ADD COLUMN emergency_status VARCHAR(50);"))
        except Exception:
            # If aid_request table doesn't exist yet or PRAGMA fails, ignore here
            pass
        db.session.commit()
    except:
        db.session.rollback()

# --- Initialize DB ---
def init_db():
    ensure_db_and_columns()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password='admin'))
        db.session.commit()

# --- Routes ---
@app.route('/', endpoint='home')
def index():
    return render_template('index.html', current_year=datetime.utcnow().year)

# --- Stats Route ---
@app.route('/stats')
@login_required
def stats():
    total_transactions = Transaction.query.count()
    verified_transactions = Transaction.query.filter_by(status='Verified').count()
    pending_transactions = Transaction.query.filter_by(status='Pending').count()
    rejected_transactions = Transaction.query.filter_by(status='Rejected').count()
    total_requests = AidRequest.query.count()
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()

    stats_data = {
        'total_transactions': total_transactions,
        'verified': verified_transactions,
        'pending': pending_transactions,
        'rejected': rejected_transactions,
        'total_requests': total_requests,
        'recent_logs': recent_logs
    }
    return render_template('stats.html', stats=stats_data, current_year=datetime.utcnow().year)


@app.route('/check_condition', methods=['GET'])
def check_condition():
    """API helper to test realtime condition checks without submitting a request.
    Call with /check_condition?lat=12.97&lon=77.59
    Returns JSON: {status: 'Normal'|'Aid Emergency'|'Unknown', reason: '...'}
    """
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    import math
    import requests

    def haversine_km(lat1, lon1, lat2, lon2):
        R = 6371.0
        phi1 = math.radians(float(lat1))
        phi2 = math.radians(float(lat2))
        dphi = math.radians(float(lat2) - float(lat1))
        dlambda = math.radians(float(lon2) - float(lon1))
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.asin(math.sqrt(a))

    def check_realtime_condition(lat, lon):
        if not lat or not lon:
            return 'Unknown', 'No coordinates provided', None
        try:
            om_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current_weather=true"
            )
            r = requests.get(om_url, timeout=6)
            cw = None
            if r.status_code == 200:
                d = r.json()
                cw = d.get('current_weather', {})
                weather_code = cw.get('weathercode')
                windspeed = cw.get('windspeed')
                if weather_code is not None and int(weather_code) >= 95:
                    return 'Aid Emergency', f'Thunderstorm (weathercode={weather_code})', cw
                try:
                    if windspeed is not None and float(windspeed) >= 20:
                        return 'Aid Emergency', f'High wind ({windspeed})', cw
                except:
                    pass
            try:
                eon_url = 'https://eonet.gsfc.nasa.gov/api/v3/events?status=open'
                er = requests.get(eon_url, timeout=6)
                if er.status_code == 200:
                    events = er.json().get('events', [])
                    for ev in events:
                        for geom in ev.get('geometries', []):
                            coords = geom.get('coordinates')
                            if not coords:
                                continue
                            ev_lon, ev_lat = coords[0], coords[1]
                            try:
                                dist = haversine_km(lat, lon, ev_lat, ev_lon)
                                if dist <= 100:
                                    title = ev.get('title', 'Event')
                                    return 'Aid Emergency', f'Nearby event: {title} ({dist:.1f} km)', cw
                            except Exception:
                                continue
            except Exception:
                pass
            return 'Normal', 'No severe conditions detected', cw
        except Exception as e:
            return 'Unknown', f'Error checking conditions: {e}', None

    status, reason, cw = check_realtime_condition(lat, lon)
    return jsonify({'status': status, 'reason': reason, 'current_weather': cw})

# --- Submit Form (Donor) with SMS ---
@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        beneficiary_name = request.form.get('beneficiary_name')
        beneficiary_id = request.form.get('beneficiary_id')
        item = request.form.get('item')
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        donor_lat = request.form.get('donor_lat')
        donor_lon = request.form.get('donor_lon')
        photo = request.files.get('photo')
        photo_filename = None

        if photo and photo.filename:
            filename = secure_filename(photo.filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            filename = f"{timestamp}_{filename}"
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            photo_filename = filename

        def to_float(v):
            try:
                return float(v) if v else None
            except:
                return None

        # Save transaction
        t = Transaction(
            beneficiary_name=beneficiary_name,
            beneficiary_id=beneficiary_id,
            item=item,
            photo_filename=photo_filename,
            lat=to_float(lat),
            lon=to_float(lon),
            donor_lat=to_float(donor_lat),
            donor_lon=to_float(donor_lon)
        )
        db.session.add(t)
        db.session.commit()
        flash("Aid submitted successfully!", "success")
        return redirect(url_for('submit'))

    return render_template('submit.html')

# --- Request Aid ---
@app.route('/request_aid', methods=['GET', 'POST'])
def request_aid():
    if request.method == 'POST':
        name = request.form.get('name')
        contact = request.form.get('contact')
        family_id = request.form.get('family_id')
        aid_type = request.form.get('aid_type')
        description = request.form.get('description')
        lat = request.form.get('lat')
        lon = request.form.get('lon')

        def to_float(v):
            try:
                return float(v) if v else None
            except:
                return None

        # --- Realtime condition check using Open-Meteo (no API key) and NASA EONET (no API key)
        import math
        import requests

        def haversine_km(lat1, lon1, lat2, lon2):
            # Calculate great-circle distance between two points (km)
            R = 6371.0
            phi1 = math.radians(float(lat1))
            phi2 = math.radians(float(lat2))
            dphi = math.radians(float(lat2) - float(lat1))
            dlambda = math.radians(float(lon2) - float(lon1))
            a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
            return 2 * R * math.asin(math.sqrt(a))

        def check_realtime_condition(lat, lon):
            """Return (status, reason, current_weather) where status is 'Normal', 'Aid Emergency', or 'Unknown'.
            Uses Open-Meteo current_weather for thunderstorm/wind checks and EONET for nearby events.
            """
            if not lat or not lon:
                return 'Unknown', 'No coordinates provided', None

            try:
                # 1) Open-Meteo current weather
                om_url = (
                    f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                    f"&current_weather=true"
                )
                r = requests.get(om_url, timeout=6)
                cw = None
                if r.status_code == 200:
                    d = r.json()
                    cw = d.get('current_weather', {})
                    weather_code = cw.get('weathercode')
                    windspeed = cw.get('windspeed')
                    # Open-Meteo weathercode 95-99 indicates thunderstorm
                    if weather_code is not None and int(weather_code) >= 95:
                        return 'Aid Emergency', f'Thunderstorm (weathercode={weather_code})', cw
                    # strong wind threshold (m/s) ~20 m/s
                    try:
                        if windspeed is not None and float(windspeed) >= 20:
                            return 'Aid Emergency', f'High wind ({windspeed})', cw
                    except:
                        pass
                # 2) NASA EONET events (natural events) nearby
                try:
                    eon_url = 'https://eonet.gsfc.nasa.gov/api/v3/events?status=open'
                    er = requests.get(eon_url, timeout=6)
                    if er.status_code == 200:
                        events = er.json().get('events', [])
                        for ev in events:
                            for geom in ev.get('geometries', []):
                                coords = geom.get('coordinates')
                                if not coords:
                                    continue
                                # geometry coordinates might be [lon, lat]
                                ev_lon, ev_lat = coords[0], coords[1]
                                try:
                                    dist = haversine_km(lat, lon, ev_lat, ev_lon)
                                    if dist <= 100:  # within 100 km
                                        title = ev.get('title', 'Event')
                                        return 'Aid Emergency', f'Nearby event: {title} ({dist:.1f} km)', cw
                                except Exception:
                                    continue
                except Exception:
                    pass

                return 'Normal', 'No severe conditions detected', cw
            except Exception as e:
                return 'Unknown', f'Error checking conditions: {e}', None

        emergency_status, emergency_reason, current_weather = check_realtime_condition(lat, lon)

        new_request = AidRequest(
            name=name,
            contact=contact,
            family_id=family_id,
            aid_type=aid_type,
            description=description,
            lat=to_float(lat),
            lon=to_float(lon),
            emergency_status=emergency_status
        )
        db.session.add(new_request)
        db.session.commit()

        # Emit realtime event for dashboards/clients
        try:
            payload = {
                'id': new_request.id,
                'name': new_request.name,
                'contact': new_request.contact,
                'family_id': new_request.family_id,
                'aid_type': new_request.aid_type,
                'description': new_request.description,
                'lat': new_request.lat,
                'lon': new_request.lon,
                'emergency_status': emergency_status,
                'emergency_reason': emergency_reason,
                'current_weather': current_weather,
                'timestamp': new_request.timestamp.isoformat()
            }
            # broadcast to all connected clients
            socketio.emit('new_request', payload, broadcast=True)
        except Exception as e:
            print('SocketIO emit error:', e)

        # Send SMS to admin for new aid request
        try:
            sms_body = (
                f"New Aid Request Received!\n"
                f"Name: {name}\n"
                f"Contact: {contact}\n"
                f"Aid Type: {aid_type}\n"
                f"Family ID: {family_id or 'Not provided'}\n"
                f"Request ID: {new_request.id}"
            )
            sms = twilio_client.messages.create(
                body=sms_body,
                from_=app.config['TWILIO_FROM_NUMBER'],
                to=app.config['ADMIN_PHONE']
            )
            print("SMS sent successfully, SID:", sms.sid)
        except TwilioRestException as e:
            print("Twilio error:", e)
            flash('⚠ Unable to send SMS notification to admin.', 'danger')

        flash('✅ Aid request submitted successfully!', 'success')
        return redirect(url_for('home'))

    return render_template('request_aid.html')

# --- Public Map ---
@app.route('/public')
def public():
    transactions = Transaction.query.all()
    transactions_list = [
        {
            'id': t.id,
            'beneficiary_name': t.beneficiary_name,
            'item': t.item,
            'status': t.status,
            'lat': t.lat,
            'lon': t.lon,
            'donor_lat': t.donor_lat,
            'donor_lon': t.donor_lon,
            'photo_filename': t.photo_filename
        } for t in transactions
    ]
    return render_template('public.html', transactions=transactions_list)

# --- Login / Logout ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            flash(f'Welcome, {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

# --- Dashboard ---
@app.route('/dashboard')
@login_required
def dashboard():
    transactions = Transaction.query.order_by(Transaction.timestamp.desc()).all()
    aid_requests = AidRequest.query.order_by(AidRequest.timestamp.desc()).all()
    return render_template('dashboard.html', transactions=transactions, aid_requests=aid_requests, current_year=datetime.utcnow().year)

# --- Verify / Delete / Audit ---
@app.route('/verify/<int:tid>/<string:new_status>')
@login_required
def verify(tid, new_status):
    t = Transaction.query.get_or_404(tid)
    old_status = t.status
    t.status = new_status if new_status in ['Pending','Verified','Rejected'] else old_status
    db.session.commit()
    log = AuditLog(transaction_id=t.id, action=f"{old_status}→{t.status}", actor=session.get('username','admin'))
    db.session.add(log)
    db.session.commit()

    # Send SMS to admin when aid is verified
    if new_status == 'Verified':
        try:
            sms_body = (
                f"Aid Verification Complete!\n"
                f"Beneficiary: {t.beneficiary_name}\n"
                f"Item: {t.item}\n"
                f"Transaction ID: {t.id}\n"
                f"Status: Verified"
            )
            sms = twilio_client.messages.create(
                body=sms_body,
                from_=app.config['TWILIO_FROM_NUMBER'],
                to=app.config['ADMIN_PHONE']
            )
            print("SMS sent successfully, SID:", sms.sid)
        except TwilioRestException as e:
            print("Twilio error:", e)
            flash('⚠ Unable to send SMS notification to admin.', 'danger')

    flash(f"Status updated to {t.status}", "success")
    return redirect(url_for('dashboard'))

@app.route('/verify_request/<int:request_id>/<string:new_status>')
@login_required
def verify_request(request_id, new_status):
    request = AidRequest.query.get_or_404(request_id)
    
    # Create a transaction from the request if verified
    if new_status == 'Verified':
        transaction = Transaction(
            beneficiary_name=request.name,
            beneficiary_id=request.family_id,
            item=request.aid_type,
            lat=request.lat,
            lon=request.lon,
            status='Verified'
        )
        db.session.add(transaction)
        
        # Delete the request after converting to transaction
        db.session.delete(request)
        db.session.commit()
        
        # Log the action
        log = AuditLog(
            transaction_id=transaction.id,
            action=f"Aid Request → Verified Transaction",
            actor=session.get('username','admin')
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f"Aid request verified and converted to transaction", "success")
    elif new_status == 'Rejected':
        db.session.delete(request)
        db.session.commit()
        flash(f"Aid request rejected and deleted", "warning")
        
    return redirect(url_for('dashboard'))

@app.route('/delete/<int:bid>', methods=['POST'])
@login_required
def delete_beneficiary(bid):
    t = Transaction.query.get_or_404(bid)
    db.session.delete(t)
    db.session.commit()
    flash("Transaction deleted!", "success")
    return redirect(url_for('dashboard'))

@app.route('/audit')
@login_required
def audit():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    return render_template('audit.html', logs=logs)

# --- Serve Uploads ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Location Tracking API ---
@app.route('/api/update_location/<int:transaction_id>', methods=['POST'])
@login_required
def update_location():
    data = request.get_json()
    transaction_id = data.get('transaction_id')
    lat = data.get('lat')
    lon = data.get('lon')
    
    if transaction_id and lat and lon:
        transaction = Transaction.query.get_or_404(transaction_id)
        transaction.current_lat = lat
        transaction.current_lon = lon
        transaction.last_updated = datetime.utcnow()
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Missing required data'}), 400

@app.route('/api/track/<int:transaction_id>')
def track_delivery(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    return render_template('track.html', transaction=transaction)

# --- Run App ---
if __name__ == '__main__':
    with app.app_context():
        init_db()
        db.create_all()  # Ensure all tables including AidRequest are created
    # Use Socket.IO runner for realtime support
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
