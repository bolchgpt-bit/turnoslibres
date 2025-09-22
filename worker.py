import os
import redis
from rq import Worker, Queue, Connection
from app import create_app

# Create Flask app
app = create_app()

if __name__ == '__main__':
    # Get Redis connection
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    redis_conn = redis.from_url(redis_url)
    
    # Create worker
    with app.app_context():
        with Connection(redis_conn):
            worker = Worker(['notify:emails'], connection=redis_conn)
            print("Starting email worker...")
            worker.work()
