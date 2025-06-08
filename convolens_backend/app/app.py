from flask import Flask, request, jsonify
import os
import uuid
from .celery_app import init_celery
from .models import db, Conversation, ConversationStatus # Import db and models

ALLOWED_EXTENSIONS = {'txt', 'json', 'csv'}

def allowed_file(filename):
    return '.' in filename and            filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_app(config_name=None):
    app = Flask(__name__)

    # Configuration
    app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
    app.config['CELERY_BROKER_URL'] = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    app.config['CELERY_RESULT_BACKEND'] = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

    # SQLAlchemy Configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://user:password@localhost:5432/convolens_db')
    # Replace 'user:password@localhost:5432/convolens_db' with your actual DB connection string or ensure DATABASE_URL env var is set.
    # For the subtask, this default string will be present but might not connect if DB not set up.
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    # Initialize extensions
    db.init_app(app)
    init_celery(app) # Celery init might need app context for db access if tasks use db directly

    # Create DB tables if they don't exist (for development, use migrations for prod)
    with app.app_context():
        # db.drop_all() # Use with caution: drops all tables
        db.create_all()

    @app.route('/health')
    def health():
        # Add DB health check
        try:
            db.session.execute("SELECT 1")
            db_status = "OK"
        except Exception as e:
            db_status = f"Error: {e}"
        return jsonify(status="OK", database=db_status)

    @app.route('/api/upload', methods=['POST'])
    def upload_file():
        if 'file' not in request.files:
            return jsonify(error="No file part in the request"), 400

        file = request.files['file']
        original_fname = file.filename # Store original filename

        if original_fname == '':
            return jsonify(error="No selected file"), 400

        if file and allowed_file(original_fname):
            file_id = str(uuid.uuid4()) + os.path.splitext(original_fname)[1]
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_id)

            try:
                file.save(filepath)

                # Create Conversation record in DB
                new_conversation = Conversation(
                    file_id=file_id,
                    original_filename=original_fname,
                    status=ConversationStatus.UPLOADED
                )
                db.session.add(new_conversation)
                db.session.commit()

                return jsonify(message="File uploaded successfully and conversation record created.",
                               file_id=file_id,
                               conversation_id=new_conversation.id), 201
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Error saving file or creating conversation record: {e}")
                return jsonify(error=f"An error occurred: {str(e)}"), 500
        else:
            return jsonify(error="File type not allowed. Allowed types: txt, json, csv"), 400

    from .routes.analysis_routes import analysis_bp
    app.register_blueprint(analysis_bp)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)

EOL
