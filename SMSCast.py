#!/usr/bin/env python

import cgi
import urllib
import urllib2
import datetime
import keys

try:
    import simplejson as json
except ImportError:
    import simplejson as json

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
from google.appengine.api import urlfetch


import pushApiErrorStates

appkey = keys.appkey
pubkey = keys.pubkey

head = "<html><head>"
meta = "<meta name=\'txtweb-appkey\' content=\'%s\'/>"%appkey
body = "</head><body>"
end = "</body></html>"

auth_hash = keys.auth_hash
done = []


def get_cusswords(): 
	"""Makes a list for bad words filter"""
	f = open('badwords.txt')
	cuss_words = [i.replace('\n','').replace('\r','') for i in f]
	return cuss_words

def write_header(self):
	self.response.out.write(head)
	self.response.out.write(meta)
	self.response.out.write(body)
	
def end_html(self):
	self.response.out.write(end)

class Users(db.Model):
	"""Models a User entry with cellphone number and chosen username """
	username = db.StringProperty( multiline = False)
	date = db.DateTimeProperty(auto_now_add = True)
	mobile = db.StringProperty()

class msglog(db.Model):
	"""Models the log of the messages sent"""
	msg = db.StringProperty()
	date = db.StringProperty()
	arrivalDate = db.DateProperty()

def userlist_key():
	"""Constructs a datastore key for a Userlist table with userlist as its name"""
	return db.Key.from_path('Userlist', "userlist")

def msglist_key():
	"""Constructs a datastore key for a Msglist table with msglist as its name"""
	return db.Key.from_path('Msglist', "msglist")

def get_mobile():
	"""returns the list of mobile hashes from the database"""
	users = db.GqlQuery("SELECT * FROM Users")
	mobile_list = [i.mobile for i in users]
	return mobile_list

def get_username():
	"""returns a list of usernames from the database"""
	users = db.GqlQuery("SELECT * FROM Users")
	user_list = [i.username for i in users]
	return user_list

def verify_source(verifyid,message,sender,protocol):
	"""
	Verify if the request indeed came from txtweb
	Prevents potential web spamming attacks
	"""
	arguments = {"txtweb-verifyid":verifyid,"txtweb-message":message,"txtweb-mobile":sender, "txtweb-protocol":protocol}
	encoded_arguments = urllib.urlencode(arguments)
	url="http://api.txtweb.com/v3/verify" + "?" + encoded_arguments
	result = urlfetch.fetch(url)
	if("success" in result.content):
		return True
	else:
		return False

def process(message):
	"""returns the list for company's arrival date"""
	msg = message.split()
	return msg[0].split('-')

class MainPage(webapp.RequestHandler):
	def get(self):
		self.response.headers["Content-Type"] = 'text/html'
		message = cgi.escape(self.request.get('txtweb-message'))	#get hold of txtweb-message here
		sender = self.request.get('txtweb-mobile')			#get the phone hash here
		verifyid= self.request.get('txtweb-verifyid')
		protocol = self.request.get('txtweb-protocol')		
				
		cuss_words = get_cusswords()
		cuss_pr = [i for i in cuss_words if i in message.split()]	#check the message for bad words
		
		if (verify_source(verifyid,message,sender,protocol)):
			write_header(self)	
			if(message == ""):
				self.response.out.write("""
					<div>To register for placement notifications - sms 'register <yourDesiredUsername>'</div>
					<div>To check for notifications of the past few days - sms 'schedule'</div>
					<div>To unregister - sms 'unregister'</div>
					<div>To 92433 42000</div>
					""")
		
			elif cuss_pr:						#check for presence of cuss words
				self.response.out.write('Mind your language')		
			
			elif "schedule" in message:				#keyword for checking schedule
				today = datetime.date.today()
				a = today.timetuple()
				#now = datetime.datetime(a[0],a[1],a[2],a[3],a[4],a[5])
				scheduled_msgs = db.GqlQuery("SELECT * FROM msglog WHERE arrivalDate >= DATETIME(%d,%d,%d)" %(a[0],a[1],a[2]))			
				for msg in scheduled_msgs:
					self.response.out.write('<p>%s</p>'%(msg.msg))		
			
			elif "unregister" in message:				#keyword for unregistering
				if (sender in auth_hash) and ('all' in message):#either all users
					unreg = db.GqlQuery("")
					self.response.out.write("The whole database has been unregistered")
				else:						#or the particular sender
					unreg = db.GqlQuery("SELECT * FROM Users WHERE mobile='%s'"%sender)				
					self.response.out.write("You have been unregistered successfully from this service.")
				db.delete(unreg)
		
			elif ("register" in message):				
				username = message.split(' ')[1]			#registers a particular user for the sms notification service
				user = Users(parent = userlist_key())
				mobile_list = get_mobile()
				user_list = get_username()
				if sender in mobile_list:
					self.response.out.write("You cannot register twice")
				elif username in user_list:
					self.response.out.write("This username already exists. Choose another username and try registering again")
				else:
					user.username = username
					user.mobile = sender
					user.put()
					self.response.out.write('You have registered successfully')
			
			else:								#keyword to send sms notification to all the registered users
				if sender in auth_hash:
					time = process(message)
					msglogs = msglog(parent = msglist_key())
					msglogs.msg = message
					msglogs.date = str(datetime.date.today())
					msglogs.arrivalDate = datetime.date(int(time[2]),int(time[1]),int(time[0]))
					msglogs.put()
					users = Users.gql("")
					msg = head + meta + body + message + end
					success = 0
					failure = 0
					for user in users:
						if not user in done:
							done.append(user)
							form_fields = {"txtweb-mobile":user.mobile, "txtweb-message":msg, "txtweb-pubkey":pubkey}
							form_data = urllib.urlencode(form_fields)
							result = urlfetch.fetch(url="http://api.txtweb.com/v1/push",
									payload=form_data,
									method=urlfetch.POST)
							if 'success' in result.content:
								success+=1
							else:
								failure+=1
					if success == 1:
						self.response.out.write("<div>Message sent successfully to %d user</div>" %success)
					else:
						self.response.out.write("<div>Message sent successfully to %d users</div>" %success)
					if failure == 1:						
						self.response.out.write("<div>Failed to send to %d user</div>" %failure)
					elif failure > 0:							
						self.response.out.write("<div>Failed to send to %d user</div>" %failure)	
				else:	
					self.response.out.write('You are not authorized to use this feature')
	
			end_html(self)

application = webapp.WSGIApplication([('/', MainPage)], debug=True)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()


