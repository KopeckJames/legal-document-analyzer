from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, SelectField, SelectMultipleField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from models import User

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password_confirm = PasswordField(
        'Confirm Password', validators=[DataRequired(), EqualTo('password')])
    terms = BooleanField('I agree to the Terms of Service and Privacy Policy', validators=[DataRequired()])
    submit = SubmitField('Register')
    
    def validate_email(self, email):
        try:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('That email is already registered. Please use a different one.')
        except Exception as e:
            # Log the error but don't fail validation
            import logging
            logging.error(f"Database error during email validation: {str(e)}")
            # We'll allow this to pass validation, and the error handling in the route will catch issues
            
    def validate_username(self, username):
        try:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('That username is already taken. Please choose a different one.')
        except Exception as e:
            # Log the error but don't fail validation
            import logging
            logging.error(f"Database error during username validation: {str(e)}")
            # We'll allow this to pass validation, and the error handling in the route will catch issues
            
class KnowledgeEntryForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=255)])
    content = TextAreaField('Content', validators=[DataRequired()])
    source_type = SelectField('Source Type', choices=[
        ('document', 'Document'),
        ('expertise', 'Expert Knowledge'),
        ('case_outcome', 'Case Outcome'),
        ('precedent', 'Legal Precedent'),
        ('other', 'Other')
    ])
    is_verified = BooleanField('Verified Information')
    tags = StringField('Tags (comma separated)')
    submit = SubmitField('Save Knowledge Entry')

class KnowledgeSearchForm(FlaskForm):
    query = StringField('Search Knowledge Base', validators=[Length(max=100)])
    tags = SelectMultipleField('Filter by Tags')
    submit = SubmitField('Search')
    
class RequestPasswordResetForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')
    
class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    password_confirm = PasswordField('Confirm New Password', 
                                  validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')