from flask import Blueprint, render_template, request, flash, redirect, url_for
from .models import User, UserWrapper
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from flask_login import login_user, login_required, LoginManager, logout_user, current_user
import re

auth = Blueprint('auth', __name__)

# Regex patterns for validation
regex_email = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')
regex_username = re.compile(r'^[a-zA-Z0-9_.-]+$')
regex_password = re.compile(r'[A-Za-z0-9@#$]{6,12}')

# Validation functions
def isValidEmail(email):
    return bool(re.fullmatch(regex_email, email))


def isValidUsername(username):
    return bool(re.fullmatch(regex_username, str(username)))


def isValidPassword(password):
    return bool(re.fullmatch(regex_password, password))

def isValidPhonenumber(phonenumber):
    try:
        return int(phonenumber) and len(phonenumber) == 10
    except:
        return False



@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        users = User.get_by_email(email)
        if users and len(users) > 0:
            user_doc = users[0]
            user = UserWrapper(user_doc)
            if check_password_hash(user.password, password):
                flash('Login Successfully!', category='success')
                login_user(user, remember=True)
                return redirect(url_for('views.home'))
        flash('Incorrect email or password, try again.', category='error')

    return render_template('login.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth.route('/sign-up', methods=['GET', 'POST'])
def sign_up_post():
    if request.method == 'POST':
        email = request.form.get('email') or ""
        name = request.form.get('name')  # get the name from the form
        username = request.form.get('username')
        password1 = request.form.get('password1')
        password2 = request.form.get('password2')

        email_exists = User.get_by_email(email)
        username_exists = User.get_by_email(username)

        if not email:
            flash('Email is required.', category='error')
        elif email_exists:
            flash('There is an account with this email. Please try another email.', category='error')
        elif not isValidEmail(email):
            flash('Invalid email! Please try again.', category='error')
        elif username_exists:
            flash('Username has been taken, try another username.', category='error')
        elif not isValidUsername(username):
            flash('Invalid username! Please try again.', category='error')
        elif not isValidPassword(password1):
            flash('Invalid password! Please try again.', category='error')
        elif password1 != password2:
            flash('Passwords don\'t match.', category='error')
        else:
            user_doc = User.create(email=email, name=name, username=username,
                                   password=generate_password_hash(password1, method='scrypt'))
            new_user = UserWrapper(user_doc)
            login_user(new_user, remember=True)
            flash('Account created', category='success')
            return redirect(url_for('views.home'))

    return render_template('sign_up.html')
