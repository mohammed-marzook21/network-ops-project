"""
Creates the two DE2 training files:
- A valid file (data/landing/sms-call-internet-mi-2013-11-08.csv)
- An invalid file, missing the 'internet' column (data/landing/sms-call-internet-mi-2013-11-09.csv)
"""
import os

os.makedirs("data/landing", exist_ok=True)

# Valid file
valid_header = "datetime,CellID,countrycode,smsin,smsout,callin,callout,internet"
valid_rows = [
    f"2013-11-08 {h:02d}:00:00,{grid},39,1.234,0.987,0.5,0.3,10.5"
    for grid in [1, 2, 3]
    for h in range(24)
]
with open("data/landing/sms-call-internet-mi-2013-11-08.csv", "w") as f:
    f.write(valid_header + "\n")
    f.write("\n".join(valid_rows) + "\n")
print("Created valid file: sms-call-internet-mi-2013-11-08.csv")

# Invalid file - missing 'internet' column
invalid_header = "datetime,CellID,countrycode,smsin,smsout,callin,callout"
invalid_rows = [
    f"2013-11-09 {h:02d}:00:00,{grid},39,1.234,0.987,0.5,0.3"
    for grid in [1, 2, 3]
    for h in range(24)
]
with open("data/landing/sms-call-internet-mi-2013-11-09.csv", "w") as f:
    f.write(invalid_header + "\n")
    f.write("\n".join(invalid_rows) + "\n")
print("Created invalid file: sms-call-internet-mi-2013-11-09.csv (missing 'internet' column)")