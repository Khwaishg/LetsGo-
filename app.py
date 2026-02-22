from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "secret_key_here"
upload_folder = "static/profile_pics"
app.config["upload_folder"]=upload_folder
DB_FILE = "users.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def create_table():
    if not os.path.exists(DB_FILE):
        conn = get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                profile_pic TEXT DEFAULT 'default.jpg',
                gender TEXT,
                age INTEGER,
                is_student TEXT,
                profile_saved INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

create_table()

@app.route("/", methods=["GET", "POST"])
def index():
    message = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = username
            return redirect(url_for('home'))
        else:
            message = "User not found. You need to signup."
    return render_template("index.html", message=message)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    message = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        if password != confirm_password:
            message = "Passwords do not match."
            return render_template("signup.html", message=message)
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password, profile_pic, gender, age, is_student) VALUES (?, ?, ?, ?, ?, ?)",
                (username, password, None, None, None, None)
            )
            conn.commit()
            user = conn.execute(
                "SELECT id FROM users WHERE username=?", (username,)
            ).fetchone()

            session.clear()
            session["user_id"] = user["id"]
            session["username"] = username
            return redirect(url_for('home'))
        except sqlite3.IntegrityError:
            message = "Username already exists."
        conn.close()
    return render_template("signup.html", message=message)

@app.route("/home")
def home():
    if "username" not in session:
        return redirect("/")
    return render_template("home.html")

@app.route("/profile")
def profile():
    if "username" not in session:
        return redirect("/")
    conn=get_db()
    user = conn.execute(
        "SELECT username, profile_pic, gender, age, is_student, profile_saved FROM users WHERE username = ?", 
        (session["username"],)
    ).fetchone()
    conn.close()
    return render_template("profile.html", user=user)

@app.route("/save_profile", methods=["POST"])
def save_profile():
    if "username" not in session:
        return redirect("/")
    username = session["username"]
    gender = request.form.get("gender")
    age = request.form.get("age")
    is_student = request.form.get("student")
    file = request.files.get("profile_pic")
    filename = None
    if file and file.filename !="":
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["upload_folder"], filename))
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
                 UPDATE users
                 SET profile_pic = ?, gender = ?, age=?, is_student=?, profile_saved = 1
                 WHERE username=?
                """, (filename, gender, age, is_student, username))
    conn.commit()
    conn.close()
    return redirect("/home")

@app.route("/edit_profile")
def edit_profile():
    if "username" not in session:
        return redirect("/")
    return render_template("edit_profile.html")

def create_friends_table():
    conn = get_db()
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS friends(
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 sender_id INTEGER,
                 receiver_id INTEGER,
                 status TEXT CHECK(status IN ('pending', 'accepted', 'rejected')) DEFAULT 'pending')
                """)
    conn.commit()
    conn.close()

create_friends_table()

def create_notifications_table():
    conn = get_db()
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS notifications(
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 user_id INTEGER,
                 message TEXT,
                 is_read INTEGER DEFAULT 0)
                """)
    conn.commit()
    conn.close()

create_notifications_table()

@app.route("/friends")
def friends():
    if "user_id" not in session:
        return redirect("/")
    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
                 SELECT DISTINCT u.id, u.username, u.profile_pic
                 FROM users u
                 WHERE u.id IN(
                   SELECT receiver_id FROM friends WHERE sender_id = ? AND status = 'accepted'
                   UNION
                   SELECT sender_id FROM friends WHERE receiver_id = ? AND status = 'accepted'
                   )
                 AND u.id != ?
                """, (user_id, user_id, user_id)) 
    friends_list = cursor.fetchall()
    friends_list = [dict(f) for f in friends_list]
    for u in friends_list:
        if u["profile_pic"]:
            u["profile_pic"] = url_for('static', filename = "profile_pics/" + u["profile_pic"])
        else:
            u["profile_pic"] = url_for('static', filename = "profile_pics/default.jpg")
    conn.close()
    return render_template("friends.html", friends = friends_list)

@app.route("/add_friends")
def add_friends():
    if "user_id" not in session:
        return redirect("/")
    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
                 SELECT id, username, profile_pic
                 FROM users
                 WHERE id != ? 
                 AND id NOT IN (
                    SELECT receiver_id FROM friends where sender_id = ?
                    UNION
                    SELECT sender_id FROM friends WHERE receiver_id = ?)
                 """, (user_id, user_id, user_id))
    users = cursor.fetchall()
    users = [dict(u) for u in users]
    for u in users:
        if u["profile_pic"]:
            u["profile_pic"] = url_for('static', filename = "profile_pics/" + u["profile_pic"])
        else:
            u["profile_pic"] = url_for('static', filename = "profile_pics/default.jpg")
    conn.close()
    return render_template("add_friends.html", users=users)

@app.route("/add_friend/<int:receiver_id>")
def add_friend(receiver_id):
    sender_id = session["user_id"]
    if sender_id == receiver_id:
        return redirect("/add_friends")
    conn = get_db()
    conn.execute("""
                 INSERT INTO friends(sender_id, receiver_id, status)
                 VALUES(?, ?, 'pending')
                """, (sender_id, receiver_id))
    conn.commit()
    conn.close()
    return redirect("/friends") 

@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect("/")

    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    # Friend requests
    cur.execute("""
        SELECT 'friend' AS type, u.id, u.username, u.profile_pic, NULL AS message
        FROM users u
        JOIN friends f ON u.id = f.sender_id
        WHERE f.receiver_id = ?
        AND f.status = 'pending'
    """, (user_id,))
    friend_notifications = cur.fetchall()

    # Travel notifications
    cur.execute("""
        SELECT 'travel' AS type, NULL AS id, NULL AS username, NULL AS profile_pic, message
        FROM notifications
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,))
    travel_notifications = cur.fetchall()

    conn.close()

    all_notifications = list(friend_notifications) + list(travel_notifications)

    return render_template("notifications.html", notifications=all_notifications)

@app.route("/clear_notifications")
def clear_notifications():
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db()
    conn.execute("DELETE FROM notifications WHERE user_id=?", (session['user_id'],))
    conn.commit()
    conn.close()

    return redirect('/notifications')

@app.route("/accept/<int:sender_id>")
def accept_request(sender_id):
    if "user_id" not in session:
        return redirect("/")
    receiver_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
                UPDATE friends
                SET status='accepted'
                WHERE sender_id = ? AND receiver_id = ?
            """, (sender_id, receiver_id))
    cur.execute("""
                INSERT INTO notifications (user_id, message)
                VALUES(?, 'Your friend request was accepted')
            """, (sender_id, ))
    conn.commit()
    conn.close()
    return redirect("/notifications")

@app.route("/reject/<int:sender_id>")
def reject_request(sender_id):
    if "user_id" not in session:
        return redirect("/")
    receiver_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
                UPDATE friends
                SET status='rejected'
                WHERE sender_id = ? AND receiver_id = ?
            """, (sender_id, receiver_id))
    cur.execute("""
                INSERT INTO notifications (user_id, message)
                VALUES(?, 'Your friend request was rejected')
            """, (sender_id, ))
    conn.commit()
    conn.close()
    return redirect("/notifications")

def create_travel_requests_table():
    conn = get_db()
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS travel_requests(
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 creator_id INTEGER,
                 destination TEXT,
                 start_date TEXT,
                 end_date TEXT,
                 min_age INTEGER,
                 max_age INTEGER,
                 travel_type TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
                """)
    conn.commit()
    conn.close()

create_travel_requests_table()

def create_responses_table():
    conn = get_db()
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS travel_responses(
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 request_id INTEGER,
                 responder_id INTEGER,
                 status TEXT)
                """)
    conn.commit()
    conn.close()

create_responses_table()

@app.route("/travel/<travel_type>")
def travel_page(travel_type):
    if "user_id" not in session:
        return redirect("/")
    user_id = session["user_id"]
    destination = request.args.get("destination", "")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    min_age = request.args.get("min_age", "")
    max_age = request.args.get("max_age", "")
    conn = get_db()
    cur = conn.cursor()
    query = """
    SELECT tr.*, u.username, u.profile_pic
    FROM travel_requests tr
    JOIN users u ON tr.creator_id = u.id
    WHERE tr.travel_type = ?
    AND tr.creator_id != ?
"""
    params = [travel_type, user_id]

    if travel_type == "known":
        query += """
        AND tr.creator_id IN (
            SELECT receiver_id FROM friends 
            WHERE sender_id=? AND status='accepted'
            UNION
            SELECT sender_id FROM friends 
            WHERE receiver_id=? AND status='accepted'
        )
        """
        params.extend([user_id, user_id])
        query += """
            AND tr.id NOT IN(
                SELECT request_id FROM travel_responses
                WHERE responder_id = ?
            )
        """
        params.append(user_id)

    elif travel_type == "new":
        query += """
        AND tr.creator_id NOT IN (
            SELECT receiver_id FROM friends 
            WHERE sender_id=? AND status='accepted'
            UNION
            SELECT sender_id FROM friends 
            WHERE receiver_id=? AND status='accepted'
        )
        AND tr.creator_id != ?
        """
        params.extend([user_id, user_id, user_id])

        query += """
        AND tr.id NOT IN(
            SELECT request_id FROM travel_responses
            WHERE responder_id = ?
        )
        """
        params.append(user_id)
    if destination:
        query += " AND tr.destination LIKE ?"
        params.append(f"%{destination}%")
    if start_date and end_date:
        query += " AND tr.start_date <= ? AND tr.end_date >= ?"
        params.extend([end_date, start_date])
    if min_age and max_age:
        query += " AND u.age BETWEEN ? AND ?"
        params.extend([min_age, max_age])

    cur.execute(query, params)
    request_lists = cur.fetchall()
    conn.close()
    return render_template("travel_with_new.html" if travel_type=='new' else "travel_with_known.html", requests=request_lists)

@app.route('/add_trip/<travel_type>', methods=['POST'])
def add_trip(travel_type):
    user_id = session['user_id']
    destination = request.form.get("destination", "")
    start_date = request.form.get("start_date", "")
    end_date = request.form.get("end_date", "")
    min_age = request.form.get("min_age", "")
    max_age = request.form.get("max_age", "")
    conn = get_db()
    conn.execute("""
                INSERT INTO travel_requests
                (creator_id, destination, start_date, end_date, min_age, max_age, travel_type)
                VALUES(?, ?, ?, ?, ?, ?, ?)
            """, (user_id, destination, start_date, end_date, min_age, max_age, travel_type))
    conn.commit()
    conn.close()
    return redirect(f'/travel/{travel_type}')

@app.route("/respond_trip/<int:request_id>/<status>")
def respond_trip(request_id, status):
    user_id = session['user_id']

    if status not in ['accepted', 'rejected']:
        return "Invalid action"

    conn = get_db()
    cur = conn.cursor()

    # Check if already responded
    cur.execute("""
        SELECT * FROM travel_responses
        WHERE request_id=? AND responder_id=?
    """, (request_id, user_id))

    already = cur.fetchone()

    if already:
        conn.close()
        return redirect(request.referrer)

    # Insert response
    cur.execute("""
        INSERT INTO travel_responses (request_id, responder_id, status)
        VALUES (?, ?, ?)
    """, (request_id, user_id, status))

    conn.commit()

    # 🔥 Notify creator
    if status == 'accepted':
        cur.execute("""
            SELECT creator_id, destination FROM travel_requests WHERE id=?
        """, (request_id,))
        data = cur.fetchone()

        creator_id = data[0]
        destination = data[1]

        conn.execute("""
            INSERT INTO notifications (user_id, message)
            VALUES (?, ?)
        """, (creator_id, f"{session['username']} accepted your trip to {destination}. Send a friend request to chat."))

        conn.commit()

    conn.close()

    #  Stay on same page (NO REDIRECT TO CHAT)
    return redirect(request.referrer)

@app.route("/reset_trips")
def reset_trips():
    conn = get_db()
    conn.execute("DELETE FROM travel_requests")
    conn.execute("DELETE FROM travel_responses")
    conn.commit()
    conn.close()
    return "Trips reset successfully"

@app.route("/my_trips")
def my_trips():
    if "user_id" not in session:
        return redirect("/")

    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT tr.*,
        (SELECT COUNT(*) 
         FROM travel_responses 
         WHERE request_id = tr.id 
         AND status = 'accepted') AS accepted_count
        FROM travel_requests tr
        WHERE creator_id = ?
        ORDER BY created_at DESC
    """, (user_id,))

    trips = cur.fetchall()
    conn.close()

    return render_template("my_trips.html", trips=trips)

@app.route("/delete_trip/<int:trip_id>")
def delete_trip(trip_id):
    if "user_id" not in session:
        return redirect("/")

    user_id = session["user_id"]
    conn = get_db()
    conn.execute("""
        DELETE FROM travel_requests
        WHERE id = ? AND creator_id = ?
    """, (trip_id, user_id))
    conn.execute("""
        DELETE FROM travel_responses
        WHERE request_id = ?
    """, (trip_id,))

    conn.commit()
    conn.close()

    return redirect("/my_trips")

@app.route("/edit_trip/<int:trip_id>", methods=["GET", "POST"])
def edit_trip(trip_id):
    if "user_id" not in session:
        return redirect("/")

    user_id = session["user_id"]
    conn = get_db()

    if request.method == "POST":
        destination = request.form["destination"]
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]
        min_age = request.form["min_age"]
        max_age = request.form["max_age"]

        conn.execute("""
            UPDATE travel_requests
            SET destination=?, start_date=?, end_date=?, min_age=?, max_age=?
            WHERE id=? AND creator_id=?
        """, (destination, start_date, end_date, min_age, max_age, trip_id, user_id))

        conn.commit()
        conn.close()
        return redirect("/my_trips")

    trip = conn.execute("""
        SELECT * FROM travel_requests
        WHERE id=? AND creator_id=?
    """, (trip_id, user_id)).fetchone()

    conn.close()
    return render_template("edit_trip.html", trip=trip)

def create_messages_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

create_messages_table()

@app.route("/send_message", methods=["POST"])
def send_message():
    data = request.get_json()
    sender = session["user_id"]
    receiver = data["receiver"]
    message = data["message"]

    conn = get_db()
    conn.execute("""
        INSERT INTO messages (sender_id, receiver_id, message)
        VALUES (?, ?, ?)
    """, (sender, receiver, message))
    conn.commit()
    conn.close()

    return {"status": "ok"}

@app.route("/get_messages/<int:other_user>")
def get_messages(other_user):
    user_id = session["user_id"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM messages
        WHERE 
        (sender_id=? AND receiver_id=?)
        OR
        (sender_id=? AND receiver_id=?)
        ORDER BY created_at
    """, (user_id, other_user, other_user, user_id))

    rows = cur.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "message": r["message"],
            "sender": "me" if r["sender_id"] == user_id else "other"
        })

    return result

@app.route("/chat/<int:other_user_id>")
def chat(other_user_id):
    if "user_id" not in session:
        return redirect("/")

    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    #  Allow chat ONLY if they are accepted friends
    cur.execute("""
        SELECT * FROM friends
        WHERE 
        ((sender_id=? AND receiver_id=?) OR
        (sender_id=? AND receiver_id=?))
        AND status='accepted'
    """, (user_id, other_user_id, other_user_id, user_id))

    is_friend = cur.fetchone()
    conn.close()

    if not is_friend:
        return "Chat allowed only with friends"

    return render_template("chat.html", other_user_id=other_user_id)

if __name__ == "__main__":
    app.run(debug=True)