from flask import Flask, jsonify, render_template, request, redirect, url_for, session
import json
import os
from bsvlib import Wallet
from bsvlib.constants import Chain

app = Flask(__name__)
app.secret_key = '123'  # needed for session

# Load users from file
def load_users():
    if os.path.exists("users.json"):
        with open("users.json", "r") as f:
            return json.load(f)
    return {}

from datetime import datetime

def create_user(username, other_data):
    users = load_users()
    if username not in users:
        join_str = datetime.utcnow().strftime("Joined %B %Y")  # e.g. "Joined May 2025"
        users[username] = {
            "joined": join_str,
            **other_data
        }
        save_users(users)
        return True
    return False

# Save users to file
def save_users(users):
    with open("users.json", "w") as f:
        json.dump(users, f)

@app.route('/')
def home():
    return redirect('/login')

@app.route('/index')
def index():
    return render_template('index.html')


posts = []  # each item: {'content': '...', 'comments': [...], 'likes': int}

@app.route('/wallet', methods=['GET'])
def wallet():
    return render_template('wallet.html', posts=posts)

@app.route('/post', methods=['POST'])
def post():
    content = request.form.get('content')
    if content and "user" in session:
        users = load_users()
        username = session["user"]
        user_data = users.get(username, {})
        image_filename = user_data.get("image_filename", "05.png")

        post = {
            'content': content,
            'comments': [],
            'likes': 0,
            'username': username,
            'image_filename': image_filename
        }

        posts.insert(0, post)
        return jsonify({'success': True, 'post': post})
    return jsonify({'success': False})


@app.route('/comment', methods=['POST'])
def comment():
    index = int(request.form.get('index'))
    comment_text = request.form.get('comment')

    if 0 <= index < len(posts) and comment_text and "user" in session:
        users = load_users()
        username = session["user"]
        user_data = users.get(username, {})
        image_filename = user_data.get("image_filename", "05.png")

        comment_data = {
            'text': comment_text,
            'username': username,
            'image_filename': image_filename
        }

        posts[index]['comments'].append(comment_data)
        return jsonify({'success': True, 'comment': comment_data})
    return jsonify({'success': False})
@app.route('/like', methods=['POST'])
def like():
    index = int(request.form.get('index'))
    if 0 <= index < len(posts):
        posts[index]['likes'] += 1
        return jsonify({'success': True, 'likes': posts[index]['likes']})
    return jsonify({'success': False})


@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        username = request.form["username"]
        password = request.form["password"]
        users = load_users()
        if username in users and users[username]["password"] == password:
            session["user"] = username
            return redirect(url_for('profile'))
        return "Invalid credentials", 401
    return render_template("login.html")

from bsvlib.keys import PrivateKey
from bsvlib.wallet import Wallet

@app.route('/signup', methods=["POST"])
def signup():
    username = request.form["username"]
    email = request.form["email"]
    password = request.form["password"]
    confirm = request.form["confirm"]

    if password != confirm:
        return "Passwords do not match", 400

    users = load_users()
    if username in users:
        return "User already exists", 400

    # Generate BSV address and WIF
    key = PrivateKey()
    address = key.address()
    wif = key.wif()

    # Create new user with joined date automatically set
    success = create_user(username, {
        "email": email,
        "password": password,
        "address": address,
        "wif": wif
    })

    if not success:
        return "User already exists", 400

    session["user"] = username
    return redirect(url_for('profile'))


@app.route('/profile')
def profile():
    if "user" not in session:
        return redirect(url_for('login'))

    users = load_users()
    user = users.get(session["user"])

    if not user:
        return redirect(url_for('logout'))

    wif = user.get("wif")
    wallet = Wallet(chain=Chain.MAIN)
    wallet.add_key(wif)

    try:
        balance_sats = wallet.get_balance(refresh=True)
        balance_bsv = balance_sats / 100_000_000
    except Exception as e:
        print("Error fetching balance:", e)
        balance_bsv = 0.0

    # Get stored image or default
    image_filename = user.get("image")
    if image_filename:
        image_path = image_filename  
    else:
        image_path = "default.png"  # fallback image

    return render_template("profile.html",
                           username=session["user"],
                           address=user.get("address"),
                           balance=f"{balance_bsv:.8f}",
                           name=user.get("name", "Your Name"),
                           description=user.get("description", "Your BSV profile"),
                           joined=user.get("joined"),
                           image_filename=image_path,
                           twitter=user.get("twitter", ""),
                           instagram=user.get("instagram", ""))
    

import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'eggwallet/static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/complete_profile', methods=['POST'])
def complete_profile():
    if "user" not in session:
        return redirect(url_for('login'))

    users = load_users()
    user = users.get(session["user"])

    if not user:
        return redirect(url_for('logout'))

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()

    # Handle image upload
    file = request.files.get('image')
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"{session['user']}_profile.{ext}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        user["image"] = filename

    if name:
        user["name"] = name
    # Optional: Only update description if provided; else leave unchanged
    if description:
        user["description"] = description

    twitter = request.form.get('twitter', '').strip()
    instagram = request.form.get('instagram', '').strip()

    if twitter:
        user["twitter"] = twitter
    else:
        user.pop("twitter", None)

    if instagram:
        user["instagram"] = instagram
    else:
        user.pop("instagram", None)

    save_users(users)
    return redirect(url_for('profile'))

@app.route('/api/get_balance', methods=['GET'])
def get_balance():
    if "user" not in session:
        return jsonify({'success': False, 'balance': 0}), 401

    users = load_users()
    user = users.get(session["user"])
    if not user or 'wif' not in user:
        return jsonify({'success': False, 'balance': 0}), 404

    wif = user['wif']
    try:
        wallet = Wallet(chain=Chain.MAIN)  # Or Chain.TEST if testnet
        wallet.add_key(wif)
        balance = wallet.get_balance(refresh=True)
        return jsonify({'success': True, 'balance': balance})
    except Exception as e:
        return jsonify({'success': False, 'balance': 0, 'error': str(e)}), 500


from flask import request
from bsvlib import Wallet
from bsvlib.constants import Chain

@app.route('/send_bsv', methods=['POST'])
def send_bsv():
    if "user" not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    users = load_users()
    user = users.get(session["user"])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    wif = user.get("wif")
    if not wif:
        return jsonify({'success': False, 'error': 'Wallet not configured'}), 400

    data = request.get_json()
    send_type = data.get('sendType')
    outputs = data.get('outputs')  # list of [address, amount]

    if not outputs or not isinstance(outputs, list):
        return jsonify({'success': False, 'error': 'Invalid outputs'}), 400

    try:
        # Prepare outputs as list of tuples (address, satoshis)
        tx_outputs = []
        for output in outputs:
            if not isinstance(output, list) or len(output) != 2:
                return jsonify({'success': False, 'error': 'Invalid output format'}), 400
            addr, amount = output
            if not isinstance(addr, str) or not isinstance(amount, int):
                return jsonify({'success': False, 'error': 'Invalid output data types'}), 400
            tx_outputs.append((addr, amount))

        print("Final outputs to be sent:", tx_outputs)

        # Create Wallet object with the user's WIF
        wallet = Wallet([wif])

        # Create, sign, and broadcast transaction in one go
        txid = wallet.create_transaction(outputs=tx_outputs).broadcast()

        return jsonify({'success': True, 'txid': txid})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/resolve_usernames', methods=['POST'])
def resolve_usernames():
    users = load_users()
    data = request.get_json()
    usernames = data.get('users', [])

    result = {}
    for u in usernames:
        user = users.get(u)
        if user and "address" in user:
            result[u] = user["address"]

    if len(result) != len(usernames):
     missing = set(usernames) - result.keys()
     return jsonify({'success': False, 'error': f'Missing addresses for: {", ".join(missing)}', 'addresses': result})

 


    return jsonify({'success': True, 'addresses': result})
    




@app.route('/logout')
def logout():
    session.pop("user", None)
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)
