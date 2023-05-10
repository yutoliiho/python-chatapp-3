from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import request, jsonify, make_response
import os
import openai
from system_message import chatbot_system_messages

app = Flask(__name__)
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("://", "ql://", 1)
else:
    db_path = os.path.join(os.path.dirname(__file__), 'db/chat.db')
    DATABASE_URL = 'sqlite:///{}'.format(db_path)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
db = SQLAlchemy(app)


openai.api_key = os.environ.get('OPENAI_API_KEY')

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    conversations = db.relationship('Conversation', backref='user', lazy=True)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chatbot_id = db.Column(db.Integer, nullable=False)
    messages = db.relationship('Message', backref='conversation', lazy=True)
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    response = db.Column(db.String(500), nullable=True)  # Response can be None for user messages
# Explicitly create the database tables
with app.app_context():
    db.create_all()
@app.route('/register', methods=['POST'])
def register():
    username = request.json.get('username')
    if not username:
        return make_response(jsonify({'error': 'Username is required'}), 400)
    if User.query.filter_by(username=username).first():
        return make_response(jsonify({'error': 'Username already exists'}), 400)
    user = User(username=username)
    db.session.add(user)
    db.session.commit()
    return jsonify({'success': True, 'user_id': user.id})
@app.route('/send_message', methods=['POST'])
def send_message():
    user_id = request.json.get('user_id')
    content = request.json.get('content')
    chatbot_id = request.json.get('chatbot_id')  # Add this line
    if not user_id or not content or not chatbot_id:
        return make_response(jsonify({'error': 'User ID, content, and chatbot_id are required'}), 400)
    user = User.query.get(user_id)
    if not user:
        return make_response(jsonify({'error': 'User not found'}), 404)
    # Create a new conversation if it does not exist
    conversation = Conversation.query.filter_by(user_id=user_id, chatbot_id=chatbot_id).first()
    if not conversation:
        conversation = Conversation(user_id=user_id, chatbot_id=chatbot_id)
        db.session.add(conversation)
        db.session.commit()
    # Add the user's message to the conversation
    user_message = Message(conversation_id=conversation.id, content=content, response=None)
    db.session.add(user_message)
    db.session.commit()
    # Retrieve conversation history
    messages = Message.query.filter_by(conversation_id=conversation.id).all()
    conversation_history = ' '.join([msg.content for msg in messages])
    system_message = chatbot_system_messages.get(int(chatbot_id), "You are a virtual sweetheart.")
    # Generate AI response using OpenAI API with conversation history as context
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_message},
            *[
                {"role": "user" if i % 2 == 0 else "assistant", "content": msg.content}
                for i, msg in enumerate(messages)
            ],
            {"role": "user", "content": content},
        ],
        max_tokens=50,
    )
    response_text = response['choices'][0]['message']['content'].strip()
    # Save AI response to the conversation
    ai_message = Message(conversation_id=conversation.id, content=response_text, response=None)
    db.session.add(ai_message)
    db.session.commit()
    return jsonify({'response_text': response_text})
@app.route('/get_messages', methods=['GET'])
def get_messages():
    user_id = request.args.get('user_id')
    chatbot_id = request.args.get('chatbot_id')  # Add this line
    # Add this block to check for chatbot_id and its value
    if not chatbot_id or int(chatbot_id) not in [1, 2]:
        return make_response(jsonify({'error': 'Chatbot ID is required and should be either 1 (Adam) or 2 (Eve)'}), 400)
    if not user_id:
        return make_response(jsonify({'error': 'User ID is required'}), 400)
    user = User.query.get(user_id)
    if not user:
        return make_response(jsonify({'error': 'User not found'}), 404)
    
    # Retrieve the conversation associated with the user
    conversation = Conversation.query.filter_by(user_id=user_id, chatbot_id=chatbot_id).first()
    if not conversation:
        return make_response(jsonify({'error': 'Conversation not found'}), 404)
    
    # Retrieve all messages in the conversation
    messages = Message.query.filter_by(conversation_id=conversation.id).all()
    messages_data = [
        {'content': message.content, 'response': message.response} for message in messages
    ]
    return jsonify({'messages': messages_data})
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)