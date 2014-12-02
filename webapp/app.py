import os
import json,httplib,urllib
import random, string
from tempfile import mkstemp
from os.path import basename
from flask import Flask, session, redirect, url_for, escape, request, render_template
from werkzeug import secure_filename
from boto.s3.connection import S3Connection
from boto.s3.key import Key

# macros
UPLOAD_FOLDER = '/home/ubuntu/streamer/webapp/tmpfiles'
STATIC_FOLDER = '/home/ubuntu/streamer/webapp/static'

ALLOWED_EXTENSIONS = set(['mp3', 'm4a', 'txt'])

app = Flask(__name__)
app.secret_key = 'X\x90N!L\x90\xb7\xb9\xf3\x86"M\xa6\xbd\xc2\xe2r\xe2)p\xa1\xa9\x11\x93'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
#app.config['STATIC_FOLDER'] = STATIC_FOLDER
app.debug = True

@app.route('/')
def index():
	
	print 'func: index'

	# if login already
	if 'username' in session:
		return app.send_static_file('upload.html')
	
	return app.send_static_file('loginui.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		
		# check PARSE DB
		if verify_login(request.form['username'], request.form['password']):
			session['username'] = request.form['username']
			return app.send_static_file('upload.html')
		else:
			return app.send_static_file('error_login_error.html')

	return render_template('loginui.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup_func():
	return app.send_static_file('signup.html')		

@app.route('/do_signup', methods=['GET', 'POST'])
def do_signup():
	if request.method == 'POST':
		uname = request.form['username']
		upass = request.form['password']

		# bad input
		if (len(uname) == 0 or len(upass) == 0):
			return app.send_static_file('error_signup_bad_input.html')

		# check existence
		if check_if_user_exists(uname):
			return app.send_static_file('error_account_exists.html')

		# the name is okay, let's do something else
		if create_account (uname, upass):
			return app.send_static_file('upload.html')
	return app.send_static_file('signup.html')

@app.route('/file', methods=['GET', 'POST'])
def upload():
	if request.method == 'POST':
		file = request.files['file']
        
		if file and allowed_file(file.filename):
			
			user_filename = file.filename
			descriptive_name, ext_filename = os.path.splitext(file.filename)
			unique_filename = random_name(16) + ext_filename

			print 'user_filename = ' + user_filename
			print 'ext_filename = ' + ext_filename
			print 'unique_filename = ' + unique_filename
			print 'descriptive_name = ' + descriptive_name

			# save to the local file system
			local_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
			file.save (local_path)
			
			# upload file to s3
			upload_file (local_path, unique_filename)

			# update PARSE - insert file into music db
			url = 'http://d2btqy3zmzx3ld.cloudfront.net/' + unique_filename
			print 'descriptive_name = ' + descriptive_name
			update_music_db (descriptive_name, url)
			
			# update PARSE - create user-music relation
			update_user_db ()

			# remove temp file
			os.remove (local_path)
	
	return app.send_static_file('success_upload.html')

@app.route('/go_back', methods=['GET', 'POST'])
def go_back():
	return app.send_static_file('upload.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
	print 'logout'
    # remove the username from the session if it's there
	session.pop('username', None)
	return app.send_static_file('loginui.html')

# utility function
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

# verify login
def verify_login(username, password):

	connection = httplib.HTTPSConnection('api.parse.com', 443)
	params = urllib.urlencode({"where":json.dumps({
       "name": username,
       "password": password
     })})
	connection.connect()
	connection.request('GET', '/1/classes/user?%s' % params, '', {
       "X-Parse-Application-Id": "5FB5GBQ6aynPJKyREO0HbdNp6xS6szxtFOwg1qJF",
       "X-Parse-REST-API-Key": "KJntVTuEDKSsvDtZvHx5i6SfUjuIjSlKdvpdM96G"
     })
	
	result = json.loads(connection.getresponse().read())
	r = result['results']
	print r

	if len(r) == 0:
		return False

	if 'name' in r[0] and 'password' in r[0]:
		if result['results'][0]['name'] == username and result['results'][0]['password'] == password:
			return True
	
	return False

# query PARSE db to get the user object id
# Used for update user db (relational part)
def get_current_user_object_id():
	connection = httplib.HTTPSConnection('api.parse.com', 443)
	params = urllib.urlencode({"where":json.dumps({
       "name": session['username']
     })})
	connection.connect()
	connection.request('GET', '/1/classes/user?%s' % params, '', {
       "X-Parse-Application-Id": "5FB5GBQ6aynPJKyREO0HbdNp6xS6szxtFOwg1qJF",
       "X-Parse-REST-API-Key": "KJntVTuEDKSsvDtZvHx5i6SfUjuIjSlKdvpdM96G"
     })
	
	result = json.loads(connection.getresponse().read())
	r = result['results']

	if 'name' in r[0]:
		print r[0]['objectId']
		return r[0]['objectId']

	return None

# upload file to s3
def upload_file (local_path, remote_name):

	conn = S3Connection('AKIAID6ALJMXGYAEC4DQ', 'nCxAtZqYiLkPhO5zpdwLt197gsMsl2dDEr5+rjNQ')
	pb = conn.get_bucket('ngnstreamer')
	k = Key(pb)
	k.name = remote_name
	k.set_metadata('Cache-Control', 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0')
	k.set_contents_from_filename(local_path)
	k.make_public ()
	return


# update PARSE database for music
def update_music_db(filename, url):
	connection = httplib.HTTPSConnection('api.parse.com', 443)
	connection.connect()
	connection.request('POST', '/1/classes/music', json.dumps({
       "name": filename,
       "url": url
     }), {
       "X-Parse-Application-Id": "5FB5GBQ6aynPJKyREO0HbdNp6xS6szxtFOwg1qJF",
       "X-Parse-REST-API-Key": "KJntVTuEDKSsvDtZvHx5i6SfUjuIjSlKdvpdM96G",
       "Content-Type": "application/json"
     })
	result = json.loads(connection.getresponse().read())

	# save object id
	session['file_id'] = result['objectId'] 
	print session['file_id'], result['objectId']

	print '----- update_music_db -----'
	print result

# update PARSE database for user
def update_user_db():

	print '----- update_user_db -----'
	file_id = session['file_id']
	user_id = get_current_user_object_id ()

	print file_id, user_id

	connection = httplib.HTTPSConnection('api.parse.com', 443)
	connection.connect()
	connection.request('PUT', '/1/classes/user/' + user_id, json.dumps({
       "songs": {
         "__op": "AddRelation",
         "objects": [
           {
             "__type": "Pointer",
             "className": "music",
             "objectId": file_id
           }
         ]
       }
     }), {
       "X-Parse-Application-Id": "5FB5GBQ6aynPJKyREO0HbdNp6xS6szxtFOwg1qJF",
       "X-Parse-REST-API-Key": "KJntVTuEDKSsvDtZvHx5i6SfUjuIjSlKdvpdM96G",
       "Content-Type": "application/json"
     })
	result = json.loads(connection.getresponse().read())
	print result
	return True

# check if the new username has been created
def check_if_user_exists (username):
	
	connection = httplib.HTTPSConnection('api.parse.com', 443)
	params = urllib.urlencode({"where":json.dumps({
       "name": username
     })})
	connection.connect()
	connection.request('GET', '/1/classes/user?%s' % params, '', {
       "X-Parse-Application-Id": "5FB5GBQ6aynPJKyREO0HbdNp6xS6szxtFOwg1qJF",
       "X-Parse-REST-API-Key": "KJntVTuEDKSsvDtZvHx5i6SfUjuIjSlKdvpdM96G"
     })
	
	result = json.loads(connection.getresponse().read())
	r = result['results']

	if len(r) == 0:
		return False

	if 'name' in r[0] and 'password' in r[0]:
		if result['results'][0]['name'] == username:
			return True
	
	return False

# create a new user account
def create_account (uname, upass):
	
	connection = httplib.HTTPSConnection('api.parse.com', 443)
	connection.connect()
	connection.request('POST', '/1/classes/user', json.dumps({
       "name": uname,
       "password": upass
     }), {
       "X-Parse-Application-Id": "5FB5GBQ6aynPJKyREO0HbdNp6xS6szxtFOwg1qJF",
       "X-Parse-REST-API-Key": "KJntVTuEDKSsvDtZvHx5i6SfUjuIjSlKdvpdM96G",
       "Content-Type": "application/json"
     })
	result = json.loads(connection.getresponse().read())

	print '----- create account -----'
	print result
	return True;


# create a random string
def random_name (length):
	return ''.join(random.choice(string.lowercase) for i in range(length))

if __name__ == '__main__':
    app.run(host='172.31.46.108')

