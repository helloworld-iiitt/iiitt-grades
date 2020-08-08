# Python standard libraries
import json
import os
import sqlite3
from datetime import date

# Third-party libraries
from flask import Flask, redirect, request, url_for, render_template
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from oauthlib.oauth2 import WebApplicationClient
import requests

# Internal imports
from db import init_db_command
from user import User

'''
grades is indexed this way: grades[Branch][Year]
grades[Branch][Year] -> Python list of csv strings

note: this could be obsolete if lot of records are there

TODO: Query from db instead of reading from file into memory
'''
# Load grades into memory
grades = [[None, None, None, None, None], [None, None, None, None, None]]

grades[0][0] = open('./cse19.csv').readlines()
grades[0][1] = open('./cse18.csv').readlines()
grades[0][2] = open('./cse17.csv').readlines()
grades[0][3] = open('./cse16.csv').readlines()
grades[0][3] = open('./cse15.csv').readlines()
grades[1][0] = open('./ece19.csv').readlines()
grades[1][1] = open('./ece18.csv').readlines()
grades[1][2] = open('./ece17.csv').readlines()
grades[1][3] = open('./ece16.csv').readlines()
grades[1][3] = open('./ece15.csv').readlines()

supp = open('./supplementary.csv').readlines()

supplementary = {}

for row in supp:
    roll_col = 0
    sub_col = 1
    grade_col = 2
    fields = row.strip().split(',')
    if fields[roll_col].strip() in supplementary.keys():
        supplementary[fields[roll_col]].append((fields[sub_col], fields[grade_col]))
    else:
        supplementary[fields[roll_col]] = [(fields[sub_col], fields[grade_col])]

def fetch_results(branch, year, email):
    '''
    Input format:
    branch: String (CSE|ECE)
    year: int (19|18|17|16)
    email: String (college given email address)

    Output:
    results: Dict (with sub code as key and grade as value)
    Also, passed, failed are part of results
    '''
    results = {}
    br = -1

    today = date.today()
    yr = today.year%100
    if today.month >= 6:
        yr-=1
    yr -= year
    email_col = 0 # this has to be manually updated according to the dataset
    roll_col = 1
    name_col = 2
    sub_start_id = 3 # this is where the grades start
    if branch == 'C':
        #  grades[0]
        br = 0
    else:
        #  grades[1]
        br = 1
    header = grades[br][yr][0].strip().split(',') # 0th row is not required
    for row in grades[br][yr]:
        fields = row.strip().split(',')
        if fields[email_col].strip() == email:
            if fields[roll_col].strip().upper() != current_user.rollno.upper():
                print('Error: Roll Number doesn\'t match')
                break
            current_user.name = fields[name_col]
            for i in range(sub_start_id, len(header)):
                results[header[i]] = fields[i].strip()
            current_user.results = json.dumps(results)
            return results

    return results

def fetch_supplementary(rollno):
    supplementary_results = {}
    if rollno in supplementary.keys():
        for t in supplementary[rollno]:
            supplementary_results[t[0]] = t[1]

    current_user.supplementary_results = json.dumps(supplementary_results)
    return supplementary_results

# Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", None)
GOOGLE_DISCOVERY_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
)

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)


# User session management setup
# https://flask-login.readthedocs.io/en/latest
login_manager = LoginManager()
login_manager.init_app(app)

try:
    init_db_command()
except sqlite3.OperationalError:
    pass

# OAuth 2 client setup
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


@app.route('/')
def index():
    return render_template('home.html', logged_in=current_user.is_authenticated, user=current_user)

def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

@app.route('/login')
def login():
    # Find out what URL to hit for Google login
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]
    # Use library to construct the request for Google login and provide
    # scopes that let you retrieve user's profile from Google
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)

@app.route('/login/callback')
def callback():
    code = request.args.get('code')
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg['token_endpoint']
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_endpoint=request.url,
        redirect_url=request.base_url,
        code=code
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    client.parse_request_body_response(json.dumps(token_response.json()))

    userinfo_endpoint = google_provider_cfg['userinfo_endpoint']
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)
    if userinfo_response.json().get('email_verified'):
        unique_id = userinfo_response.json()['sub']
        email = userinfo_response.json()['email']
        name = userinfo_response.json()['name']
    else:
        return "User email not verified", 400
    rollno = ''
    email2roll = open('./email_roll.csv').readlines()
    for item in email2roll:
        em, rno = item.split(',')
        if em.strip() == email:
            rollno = rno.strip().upper()
            break

    if rollno == '':
        # means they logged in from some other mail id
        return (
            '<h2>Please login with your institue mail id</h2>'
            '<p>If you did login with your institue mail id, you must be a faculty and this portal is for students. If you think there is some problem and your results are missing, please contact the class coordinator or faculty advisor or member of Web Dev-IIITT</p>'
            '<a href="/logout" class="btn btn-primary">Logout</a>'
        )
    user = User(unique_id, name, email, rollno)
    # Doesn't exist? Add it to the database.
    if not User.get(unique_id):
        User.create(unique_id, name, email, rollno)

    # Begin user session by logging the user in
    login_user(user)
    return redirect(url_for('index'))

@app.route('/getresults')
@login_required
def getresults():
    year = int(current_user.rollno[3:5])
    branch = current_user.rollno[0].upper()
    results = fetch_results(branch.upper(), year, current_user.email)
    if len(results) == 0:
        return (
            '<h2>Error has occurred. Please contact the class coordinator</h2>'
            '<h4>Your results were not found</h4>'
            '<a href="/">Click here to go to home page</a>'
            '<br />'
            '<a href="/logout" class="btn btn-primary">Click here to Logout</a>'
        )
    return render_template('results.html', user=current_user, results=results)

@app.route('/getsupplementary')
def getsupplementary():
    if current_user.is_authenticated:
        if current_user.rollno == '':
            return (
                '<h2>Error has occurred. Please contact the class coordinator</h2>'
                '<h4>Your results were not found</h4>'
                '<a href="/">Click here to go to home page</a>'
                '<br />'
                '<a href="/logout" class="btn btn-primary">Click here to Logout</a>'
            )
        results = fetch_supplementary(current_user.rollno)
        if len(results) == 0:
            return (
                '<h1>No results</h1>'
                '<p>If you think there is some problem and your results are missing, please contact the class coordinator or faculty advisor</p>'
                '<a href="/">Click here to go to home page</a>'
                '<br />'
                '<a href="/logout" class="btn btn-primary">Click here to Logout</a>'
            )
        return render_template('results.html', user=current_user, results=results)
    else:
        return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run()
