import os
import time
import re
import requests
import smtplib
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from dotenv import load_dotenv

# Load environment variables ----------------
load_dotenv() 
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')
RECIPIENT_EMAIL = os.getenv('EMAIL_TO', SMTP_USER)
# Define Eastern Time zone (handles DST)
EST = ZoneInfo('America/New_York')

if not SMTP_USER or not SMTP_PASS:
    raise RuntimeError('SMTP_USER and SMTP_PASS must be set in the environment')
#--------------------------------------------

# ------------------------------------------
def send_email(subject: str, body: str, to_addr: str):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = to_addr
    msg.set_content(body)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)
# -------------------------------------------


# the DSM we want releases around 20:15 UTC
def find_KNYC_product_today(today, start = "20:00:00Z", stop = "21:00:00Z"):

    # get DSM for NYC (KNYC) for current date
    url = (
        "https://mesonet.agron.iastate.edu/"
        f"api/1/nws/afos/list.json?pil=DSMNYC&date={today}"
    )
    resp = requests.get(url)
    resp.raise_for_status()
    js = resp.json()



    product_id = None
    for i in range(len(js['data'])):
        file = js['data'][i]
        UTC_Time = file['entered'].split("T", 1)[1]
        if start <= UTC_Time <= stop:
            product_id = file['product_id']

    return product_id

def get_prec(product_id, date, station_code = "KOKX"):
    "Gets the precipitation given the DSM. Does checks to make sure that we are retrieving the correct data"
    if product_id == None:
        return None
    
    product_url = f"https://mesonet.agron.iastate.edu/api/1/nwstext/{product_id}"

    nws_resp = requests.get(product_url, params={'nolimit':'false'})
    nws_resp.raise_for_status()

    lines = nws_resp.text.split("\n")

    # check to see that we are in the correct station
    found_station_code = lines[1].split(" ")[1]
    if found_station_code != station_code:
        print(found_station_code)
        raise ValueError("Wrong station_code")
    
    # Check to see that we are looking at the correct date
    body = lines[3]
    code_body_split = body.split(" ")
    found_date = code_body_split[3] # This is in DD/MM format
    if found_date != date:
        raise ValueError("Wrong Date")


    # grab precipitation value
    sub_body = body.split("//")
    weather_vals = sub_body[2]
    sep_weather_vals = weather_vals.split("/")
    prec = sep_weather_vals[1]
    return prec


def poll_and_notify():
    """
    Poll the DSMNYC API every minute from 4:10 to 4:20 pm EST,
    and send an email when a numeric precipitation value is found.
    """
    today_Ymd = date.today().strftime("%Y-%m-%d")
    today_dm = date.today().strftime("%d/%m")

    # Define polling window in EST
    start_dt = datetime.combine(date.today(), dtime(16, 14, 0), tzinfo=EST)
    end_dt = datetime.combine(date.today(), dtime(16, 20, 0), tzinfo=EST)
    now = datetime.now(EST)

    # Wait until the window opens
    if now < start_dt:
        wait = (start_dt - now).total_seconds()
        print(f"Waiting {wait:.0f}s until 4:10 pm EST...")
        time.sleep(wait)

    # Poll every minute until the window closes
    while datetime.now(EST) <= end_dt:
        pid = find_KNYC_product_today(today_Ymd)
        prec = get_prec(pid, today_dm, "KOKX")
        if prec != None and (prec == "T" or float(prec) > 0):
            subject = f"DSMNYC Precipitation: {prec}\""
            body = (
                f"Found precipitation value {prec} at "
                f"{datetime.now(EST).isoformat()} for product {pid}"
            )
            send_email(subject, body, RECIPIENT_EMAIL)
            print("Email sent, exiting.")
            return

        print("No numeric precipitation found; retrying in 15s...")
        time.sleep(15)

    print("Polling window ended; no numeric precipitation found.")






if __name__=="__main__":
    poll_and_notify()

