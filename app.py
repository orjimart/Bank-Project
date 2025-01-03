from flask import Flask, render_template, url_for, request, session, flash, redirect, send_file
from flask_mail import Mail, Message
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
import random
from flask_bcrypt import Bcrypt
import re
import pdfkit
from urllib.parse import urlencode
import requests



# creating a flask instance 
app = Flask(__name__)
# Load environment variables from .env file
load_dotenv()

#secret key
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")



# db connection
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DB_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
migrate = Migrate(app, db)


# email connection
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD")

mail = Mail(app)



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    card_number = db.Column(db.String(16), unique=True)
    balance = db.Column(db.Float, default=50000.00)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    recipient_name = db.Column(db.String(100))
    recipient_card_number = db.Column(db.String(16))
    amount = db.Column(db.Float)
    type = db.Column(db.String(25))  # Add the type field
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='transactions')

    def __repr__(self):
        return f"Transaction(id={self.id}, user_id={self.user_id}, recipient_name={self.recipient_name}, " \
               f"recipient_card_number={self.recipient_card_number}, amount={self.amount}, " \
               f"type={self.type}, timestamp={self.timestamp})"


# 

def insert_hyphens(value):
    value = re.sub(r'\s', '', value)  # Remove any existing whitespace
    return re.sub(r'\d{4}(?!$)', '\\g<0>-', value)

app.jinja_env.filters['insert_hyphens'] = insert_hyphens



# routes

@app.route("/")
@app.route('/home')
def home_page():
    return render_template('index.html')


@app.route('/about')
def about_page():
    return render_template('about.html')

@app.route('/services')
def services_page():
    return render_template('services.html')

@app.route('/contact')
def contact_page():
    return render_template('contact.html')


@app.route('/submitForm', methods=['POST'])
def submit_form():
    name = request.form.get('name')
    email = request.form.get('email')
    subject = request.form.get('subject')
    message = request.form.get('message')

    msg = Message('New Form Submission', sender=email, recipients=['bwaveict@gmail.com'])
    msg.body = f"Name: {name}\nEmail: {email}\nSubject: {subject}\nMessage: {message}"

    mail.send(msg)

    return render_template('success.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Retrieve the user from the database based on the provided email
        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password, password):
            # Authentication successful, store user_id in session
            session['user_id'] = user.id
            flash('Login successful.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
            return redirect(url_for('login'))
    
    # GET request, render the login form
    return render_template('login.html')


@app.route('/logout')
def logout():
    # Clear the session data
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home_page'))


@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Perform form validation
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register_page'))
        if len(password) < 6:
            flash('Password should be at least 6 characters', 'danger')
            return redirect(url_for('register_page'))

        # Check if email already exists
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already exists. Please log in.', 'danger')
            return redirect(url_for('login'))

        # Hash the password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Generate card number
        card_number = ''.join([str(random.randint(0, 9)) for _ in range(16)])
        formatted_card_number = '-'.join([card_number[i:i+4] for i in range(0, len(card_number), 4)])



        # Create a new user
        new_user = User(full_name=full_name, email=email, password=hashed_password, card_number=card_number)
        db.session.add(new_user)
        db.session.commit()

        # Store user_id and card_number in session
        session['user_id'] = new_user.id
        session['card_number'] = formatted_card_number

        flash('Registration successful. You are now logged in.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')



@app.route('/dashboard')
def dashboard():
    # Retrieve user_id from session
    user_id = session.get('user_id')

    if user_id:
        # Retrieve the user from the database using user_id
        user = User.query.get(user_id)
        return render_template('dashboard.html', user=user)
    else:
        flash('You need to log in first.', 'danger')
        return redirect(url_for('login'))



@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    # Retrieve user_id from session
    user_id = session.get('user_id')
    if user_id:
        # Retrieve the user from the database using user_id
        user = User.query.get(user_id)

        if request.method == 'POST':
            recipient_card_name = request.form['card_name']
            recipient_card_number = request.form['card_number']
            amount = float(request.form['amount'])

            # Check if the user has sufficient balance
            if amount > user.balance:
                flash('Insufficient balance.', 'danger')
                return redirect(url_for('transfer'))

            # Retrieve the recipient user from the database using the card number
            recipient = User.query.filter_by(card_number=recipient_card_number).first()

            if recipient and recipient.full_name == recipient_card_name:
                # Check if the recipient is not the same as the sender
                if recipient.id == user.id:
                    flash('Cannot send funds to yourself.', 'danger')
                    return redirect(url_for('transfer'))

                # Update sender's balance
                user.balance -= amount

                # Update recipient's balance
                recipient.balance += amount

                # Update the database
                db.session.commit()

                # Create a new transaction record
                # transaction = Transaction(
                #     user_id=user.id,
                #     recipient_name=recipient.full_name,
                #     recipient_card_number=recipient.card_number,
                #     amount=amount,
                #     type="debit"
                # )
                # db.session.add(transaction)
                # db.session.commit()

                # Inside the transfer route
                transaction_sender = Transaction(
                    user_id=user.id,
                    recipient_name=recipient.full_name,
                    recipient_card_number=recipient.card_number,
                    amount=amount,
                    type='Debit'  # Set the transaction type to 'Debit' for the sender
                )
                transaction_recipient = Transaction(
                    user_id=recipient.id,
                    recipient_name=user.full_name,
                    recipient_card_number=user.card_number,
                    amount=amount,
                    type='Credit'  # Set the transaction type to 'Credit' for the recipient
                )
                db.session.add(transaction_sender)
                db.session.add(transaction_recipient)
                db.session.commit()

                # Generate receipt data
                receipt_data = {
                    'sender_name': user.full_name,
                    'recipient_name': recipient.full_name,
                    'recipient_card_number': recipient.card_number,
                    'amount': amount
                }

                # Generate receipt and get the filename
                receipt_filename = generate_receipt(receipt_data)

                # Redirect to the success page with the filename
                return redirect(url_for('payment', filename=receipt_filename))

            else:
                flash('Invalid recipient card name or number.', 'danger')
                return redirect(url_for('transfer'))

        return render_template('transfer.html', user=user)

    else:
        flash('You need to log in first.', 'danger')
        return redirect(url_for('login'))




@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    # Retrieve user_id from session
    user_id = session.get('user_id')
    if user_id:
        # Retrieve the user from the database using user_id
        user = User.query.get(user_id)

        if request.method == 'POST':
            card_number = request.form['card_number']
            amount = float(request.form['amount'])

            # Check if the card number matches the user's card number
            if card_number != user.card_number:
                flash('Invalid card number.', 'danger')
                return redirect(url_for('deposit'))

            # Update the user's balance
            user.balance += amount

            # Create a credit transaction record
            transaction = Transaction(
                user_id=user.id,
                recipient_name=user.full_name,
                recipient_card_number=user.card_number,
                amount=amount,
                type="Credit - Deposit"  
            )
            db.session.add(transaction)
            db.session.commit()

            flash(f'Successfully deposited ₦{amount:.2f} to your account.', 'success')
            return redirect(url_for('dashboard'))

        return render_template('deposit.html', user=user)

    else:
        flash('You need to log in first.', 'danger')
        return redirect(url_for('login'))



@app.route('/recharge', methods=['GET', 'POST'])
def recharge():
    # Retrieve user_id from session
    user_id = session.get('user_id')

    if user_id:
        # Retrieve the user from the database using user_id
        user = User.query.get(user_id)

        if request.method == 'POST':
            amount = float(request.form['amount'])

            # Calculate the discount amount (10% of the recharge amount)
            discount = amount * 0.1
            total_amount = amount - discount

            # Check if the user has sufficient balance
            if total_amount > user.balance:
                flash('Insufficient balance.', 'danger')
                return redirect(url_for('recharge'))

            # Update the user's balance
            user.balance -= total_amount

            # Update the database
            db.session.commit()

            # Create a new transaction record for the recharge
            transaction = Transaction(
                user_id=user.id,
                recipient_name=user.full_name,
                recipient_card_number=user.card_number,
                amount=-total_amount,  # Negative amount indicates a purchase
                type='Debit - Airtime Purchase'  # Transaction type is 'Debit' for a purchase
            )
            db.session.add(transaction)
            db.session.commit()

            return render_template('recharge_success.html', amount=total_amount, discount=discount)

        return render_template('recharge.html', user=user)

    else:
        flash('You need to log in first.', 'danger')
        return redirect(url_for('login'))



@app.route('/transaction_history')
def transaction_history():
    # Retrieve user_id from session
    user_id = session.get('user_id')

    if user_id:
        # Retrieve the user from the database using user_id
        user = User.query.get(user_id)

        # Retrieve the user's transactions in descending order of timestamp
        transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.timestamp.desc()).all()

        return render_template('transaction_history.html', user=user, transactions=transactions)
    
    else:
        flash('You need to log in first.', 'danger')
        return redirect(url_for('login'))


@app.route('/exchange_rate')
def exchange_rate():
    user_id = session.get('user_id')

    if user_id:
        # Retrieve the user from the database using user_id
        user = User.query.get(user_id)

        return render_template('soon.html', user=user)
    
    else:
        flash('You need to log in first.', 'danger')
        return redirect(url_for('login'))




@app.route('/download_receipt/<filename>')
def download_receipt(filename):
    # Provide the receipt file for downloading
    return send_file(filename, as_attachment=True)


@app.route('/success/<filename>')
def payment(filename):
    return render_template('payment.html', filename=filename)


@app.route('/success/<filename>/download')
def download_success_receipt(filename):
    # Provide the receipt file for downloading
    return send_file(filename, as_attachment=True)







def generate_receipt(receipt_data):
    # Define the receipt content using HTML
    receipt_content = """
   
<html style="-moz-osx-font-smoothing: grayscale; -webkit-font-smoothing: antialiased; background-color: #464646; margin: 0; padding: 0;">
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
        <meta name="format-detection" content="telephone=no">
        <title>Transaction Successful</title>
        
    </head>
    <body bgcolor="#d7d7d7" class="generic-template" style="-moz-osx-font-smoothing: grayscale; -webkit-font-smoothing: antialiased; background-color: #d7d7d7; margin: 0; padding: 0;">
        <!-- Header Start -->

        <!-- Header End -->

        <!-- Content Start -->
        <table cellpadding="0" cellspacing="0" cols="1" bgcolor="#d7d7d7" align="center" style="max-width: 600px;">
            <tr bgcolor="#d7d7d7">
                <td height="50" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
            </tr>

            <!-- This encapsulation is required to ensure correct rendering on Windows 10 Mail app. -->
            <tr bgcolor="#d7d7d7">
                <td style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;">
                    <!-- Seperator Start -->
                    <table cellpadding="0" cellspacing="0" cols="1" bgcolor="#d7d7d7" align="center" style="max-width: 600px; width: 100%;">
                        <tr bgcolor="#d7d7d7">
                            <td height="30" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                        </tr>
                    </table>
                    <!-- Seperator End -->

 <!-- Generic Pod Left Aligned with Price breakdown Start -->
                    <table align="center" cellpadding="0" cellspacing="0" cols="3" bgcolor="white" class="bordered-left-right" style="border-left: 10px solid #d7d7d7; border-right: 10px solid #d7d7d7; max-width: 600px; width: 100%;">
                        <tr height="50"><td colspan="3" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td></tr>
                        <tr align="center">
                            <td width="36" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                            <td class="text-primary" style="color: #F16522; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;">
                                <img src="http://dgtlmrktng.s3.amazonaws.com/go/emails/generic-email-template/tick.png" alt="GO" width="50" style="border: 0; font-size: 0; margin: 0; max-width: 100%; padding: 0;">
                            </td>
                            <td width="36" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                        </tr>
                        <tr height="17"><td colspan="3" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td></tr>
                        <tr align="center">
                            <td width="36" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                            <td class="text-primary" style="color: #F16522; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;">
                                <h1 style="color: #F16522; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 30px; font-weight: 700; line-height: 34px; margin-bottom: 0; margin-top: 0;">Payment Sent</h1>
                            </td>
                            <td width="36" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                        </tr>
                        <tr height="30"><td colspan="3" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td></tr>

                        <tr height="10"><td colspan="3" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td></tr>
                        <tr align="left">
                            <td width="36" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                            <td style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;">
                                <h2 style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 22px; margin: 0;">Your transaction was successful!</h2>
                                <br>
                                 <p style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 22px; margin: 0; "><strong>Payment Details:</strong><br/>

                                  <p>Sender: {sender_name}</p><br/>
                                    <p>Recipient: {recipient_name}</p><br/></p> 
                                    <br>
                             <<p>Card Number: {recipient_card_number}</p><br/>
                                <p>Amount: ₦{amount:.2f}</p>
                            </td>
                            <td width="36" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                        </tr>
                        <tr height="30">
                            <td style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                            <td style="border-bottom: 1px solid #D3D1D1; color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                            <td style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                        </tr>
                        <tr height="30"><td colspan="3" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"> Thank You for Banking with Us</td></tr>
 

                        <tr height="50">
                            <td colspan="3" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                        </tr>

                    </table>
                    <!-- Generic Pod Left Aligned with Price breakdown End -->

                    <!-- Seperator Start -->
                    <table cellpadding="0" cellspacing="0" cols="1" bgcolor="#d7d7d7" align="center" style="max-width: 600px; width: 100%;">
                        <tr bgcolor="#d7d7d7">
                            <td height="50" style="color: #464646; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; line-height: 16px; vertical-align: top;"></td>
                        </tr>
                    </table>
                    <!-- Seperator End -->

                </td>
            </tr>
        </table>

    </body>
</html>
    """.strip().format(**receipt_data)

    # Generate a unique filename for the receipt (e.g., using timestamp)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"receipt_{timestamp}.pdf"

    # Convert the HTML receipt content to PDF
    pdfkit.from_string(receipt_content, filename)

    # Return the filename so it can be used for downloading
    return filename
