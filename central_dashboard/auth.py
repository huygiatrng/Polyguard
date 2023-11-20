from flask import Blueprint, render_template, request, flash, redirect, url_for
from .models import User, UserWrapper, PhoneNumber
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
        email = request.form.get('email', "")
        name = request.form.get('name')
        username = request.form.get('username')
        password1 = request.form.get('password1')
        password2 = request.form.get('password2')
        phonenumber = request.form.get('phonenumber', "")
        countrycode = request.form.get('country_code', "")
        full_country_code = f"+{countrycode}" if countrycode else None

        if not all([email, username, password1, password2, phonenumber, full_country_code]):
            flash('All fields are required.', category='error')
            return render_template('sign_up.html')

        email_exists = User.get_by_email(email)
        username_exists = User.get_by_username(username)

        if email_exists:
            flash('Email already registered.', category='error')
        elif username_exists:
            flash('Username taken.', category='error')
        elif not isValidEmail(email) or not isValidUsername(username) or not isValidPassword(password1) or not isValidPhonenumber(phonenumber):
            flash('Invalid input.', category='error')
        elif password1 != password2:
            flash('Passwords do not match.', category='error')
        else:
            hashed_password = generate_password_hash(password1, method='scrypt')
            user_doc = User.create(email=email, name=name, username=username, password=hashed_password)
            new_user = UserWrapper(user_doc)
            PhoneNumber.create(user_id=new_user.id, phonenumber=phonenumber, countrycode=full_country_code)
            login_user(new_user, remember=True)
            flash('Account created!', category='success')
            return redirect(url_for('views.home'))

    return render_template('sign_up.html')