from app.workers.email_worker import send_test_email
import sys

def main():
    """CLI para enviar un email de prueba usando la configuración SMTP."""
    email = sys.argv[1] if len(sys.argv) > 1 else "test@example.com"
    print(f"Sending test email to {email}...")
    
    success = send_test_email(email)
    
    if success:
        print("✅ Test email sent successfully!")
    else:
        print("❌ Failed to send test email. Check your SMTP configuration.")

if __name__ == '__main__':
    main()
