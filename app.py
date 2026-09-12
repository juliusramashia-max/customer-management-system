# Your app.py should look like this:
from flask import Flask, jsonify
from config import Config
from database import init_db  # ← This should be imported

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
init_db(app)  # ← This should be called

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'Customer Management System is running'
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)