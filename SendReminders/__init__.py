import datetime
import logging
import smtplib
from email.mime.text import MIMEText
from collections import defaultdict
import os
import azure.functions as func
import pymssql  # Pure Python driver, works with Azure SQL

# --- Environment variables ---
SQL_SERVER = os.getenv("SQL_SERVER")
SQL_DB = os.getenv("SQL_DB")
SQL_USER = os.getenv("SQL_USER")
SQL_PASS = os.getenv("SQL_PASS")

SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def send_email(to_email, subject, body, is_html=False):
    """Send an email using SMTP with optional HTML support."""
    msg = MIMEText(body, "html" if is_html else "plain")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server_smtp:
        server_smtp.starttls()
        server_smtp.login(SMTP_USER, SMTP_PASS)
        server_smtp.sendmail(SMTP_USER, [to_email], msg.as_string())


def main(mytimer: func.TimerRequest) -> None:
    logging.info("Running appointment reminder function")

    try:
        # Connect to Azure SQL using pymssql
        conn = pymssql.connect(
            server=SQL_SERVER,       # e.g., 'yourserver.database.windows.net'
            user=SQL_USER,           # SQL username
            password=SQL_PASS,       # SQL password
            database=SQL_DB,
            port=1433           # TLS encryption required by Azure SQL
        )
        cursor = conn.cursor()

        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)

        # ---------------- Patient reminders ----------------
        patient_query = """
        SELECT u.email, u.name, a.date, a.time
        FROM Appointments a
        JOIN Patients p ON a.patient_id = p.id
        JOIN Users u ON p.user_id = u.id
        WHERE a.date IN (CAST(GETDATE() AS DATE), DATEADD(DAY, 1, CAST(GETDATE() AS DATE)))
        """
        cursor.execute(patient_query)

        for email, name, appt_date, appt_time in cursor.fetchall():
            if isinstance(appt_date, datetime.datetime):
                appt_date = appt_date.date()
            day_text = "today" if appt_date == today else "tomorrow" if appt_date == tomorrow else str(appt_date)

            subject = "Appointment Reminder"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <p>Hello {name},</p>
                <p>This is a reminder that you have an appointment <b>{day_text}</b> on <b>{appt_date}</b> at <b>{appt_time}</b>.</p>
                <p>Best regards,<br><b>Healthcare+</b></p>
            </body>
            </html>
            """
            send_email(email, subject, body, is_html=True)

        # ---------------- Provider consolidated reminders ----------------
        provider_query = """
        SELECT pr.id, pr.email, u.name AS provider_name, a.date, a.time, pu.name AS patient_name
        FROM Appointments a
        JOIN Providers pr ON a.provider_id = pr.id
        JOIN Patients p ON a.patient_id = p.id
        JOIN Users pu ON p.user_id = pu.id
        JOIN Users u ON pr.user_id = u.id
        WHERE a.date IN (CAST(GETDATE() AS DATE), DATEADD(DAY, 1, CAST(GETDATE() AS DATE)))
        ORDER BY pr.id, a.date, a.time
        """
        cursor.execute(provider_query)

        provider_appts = defaultdict(list)
        for provider_id, provider_email, provider_name, appt_date, appt_time, patient_name in cursor.fetchall():
            if isinstance(appt_date, datetime.datetime):
                appt_date = appt_date.date()
            provider_appts[(provider_email, provider_name)].append((appt_date, appt_time, patient_name))

        for (email, name), appts in provider_appts.items():
            subject = "Your Appointment Schedule"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>Hello Dr. {name},</h2>
                <p>Here is your upcoming schedule:</p>
                <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 600px;">
                    <tr style="background-color: #2a9d8f; color: #fff;">
                        <th>Date</th>
                        <th>Time</th>
                        <th>Patient</th>
                    </tr>
            """
            for appt_date, appt_time, patient_name in appts:
                body += f"""
                    <tr>
                        <td>{appt_date}</td>
                        <td>{appt_time}</td>
                        <td>{patient_name}</td>
                    </tr>
                """
            body += """
                </table>
                <p style="margin-top:20px;">Best regards,<br><b>Healthcare+</b></p>
            </body>
            </html>
            """
            send_email(email, subject, body, is_html=True)

        conn.close()

    except Exception as e:
        logging.error(f"Error in send_reminders: {e}")
