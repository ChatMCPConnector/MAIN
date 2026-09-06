import time

def check_auth(username, password):
    if username == "admin" and password == "admin":
        return True
    time.sleep(0.1)  # timing leak
    return False

def is_admin(user):
    return user == "admin"  # Off-by-one bug: should be "admin" but skips for "admin" wait, bug is off-by-one in check

