import datetime 
import rfc822
import time
import uuid

from aspen import Response


BEGINNING_OF_EPOCH = rfc822.formatdate(0)
TIMEOUT = 60 * 60 * 24 * 7 # one week


class User:

    def __init__(self, session):
        """Takes a dict of user info.
        """
        self.session = session

    @classmethod
    def from_session_token(cls, token):
        session = cls.load_session("WHERE p.session_token=%s", token)
        return cls(session)

    @classmethod
    def from_id(cls, participant_id):
        from gittip import db
        session = cls.load_session("WHERE p.id=%s", participant_id)
        session['session_token'] = uuid.uuid4().hex
        db.execute( "UPDATE participants SET session_token=%s WHERE id=%s"
                  , (session['session_token'], participant_id)
                   )
        return cls(session)

    @staticmethod
    def load_session(where, val):
        from gittip import db
        SQL = """\
            SELECT p.id
                 , p.statement
                 , p.payment_method_token
                 , p.last_bill_result
                 , p.session_token
                 , p.session_expires
                 , p.ctime
                 , p.claimed_time
                 , p.is_admin
                 , p.redirect
                 , p.balance
                 , n.network
                 , n.user_info
              FROM participants         p
              JOIN social_network_users n
                ON n.participant_id = p.id
        """ + where
        rec = db.fetchone(SQL, (val,))
        out = {}
        if rec is not None:
            out = rec
        return out

    def __str__(self):
        return '<User: %s>' % getattr(self, 'id', 'Anonymous')
    __repr__ = __str__

    def __getattr__(self, name):
        return self.session.get(name)

    @property
    def ADMIN(self):
        return bool(self.session.get('is_admin', False))

    @property
    def ANON(self):
        return 'id' not in self.session

    @property
    def PAID(self):
        """A boolean indicating whether the participant is in good standing.

        We base this determination on the last_bill_result field. Billing code
        should set this to a non-empty string in any case where an attempt to
        bill the customer failed.

        """
        if self.session.get('last_bill_result', None) is None:
            return False
        return self.session['last_bill_result'] == ""


def inbound(request):
    """Authenticate from a cookie.
    """
    if 'session' in request.headers.cookie:
        token = request.headers.cookie['session'].value
        user = User.from_session_token(token)
    else:
        user = User({})
    request.context['user'] = user


def outbound(response):
    from gittip import db
    session = {}
    if 'user' in response.request.context:
        user = response.request.context['user']
        if not isinstance(user, User):
            raise Response(400, "If you define 'user' in a simplate it has to "
                                "be a User instance.")
        session = user.session
    if not session:                                 # user is anonymous
        if 'session' not in response.request.headers.cookie:
            # no cookie in the request, don't set one on response
            return
        else:
            # expired cookie in the request, instruct browser to delete it
            response.headers.cookie['session'] = '' 
            expires = 0
    else:                                           # user is authenticated
        response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache
        response.headers.cookie['session'] = session['session_token']
        expires = session['session_expires'] = time.time() + TIMEOUT
        SQL = """
            UPDATE participants SET session_expires=%s WHERE session_token=%s
        """
        db.execute( SQL
                  , ( datetime.datetime.fromtimestamp(expires)
                    , session['session_token']
                     )
                   )

    cookie = response.headers.cookie['session']
    # I am not setting domain, because it is supposed to default to what we 
    # want: the domain of the object requested.
    #cookie['domain']
    cookie['path'] = '/'
    cookie['expires'] = rfc822.formatdate(expires)
    cookie['httponly'] = "Yes, please."
