# Create your views here.
from django.shortcuts import render, redirect, HttpResponseRedirect, get_object_or_404
from django.urls import reverse
from django.http import HttpResponse
import requests
import time
import re
from .models import ArxivPaper, Vote
from .forms import RegistrationForm
from django.conf import settings
from django.core.mail import send_mail, EmailMessage
import summarizer.utils as utils
from datetime import datetime, timedelta
import ast
from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views import View
import six
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth import authenticate
from django.core.exceptions import PermissionDenied
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import logout
import os
from django.utils.translation import get_language

class CustomAuthenticationForm(AuthenticationForm):
    def clean_username(self):
        print('clean')
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        user = authenticate(username=username, password=password)

        print('user',user)
        if user is not None and not user.is_active:
            print('activate brah')
            raise ValidationError("Your account is not activated yet.")
        return username

class CustomLoginView(auth_views.LoginView):
    authentication_form = CustomAuthenticationForm

    def dispatch(self, request, *args, **kwargs):
        print('dis')
        try:
            print('ok')
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied as e:
            print('pasok')
            messages.error(self.request, str(e))
            return self.form_invalid(self.get_form())

    def form_valid(self, form):
        print('not perm a')

        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        try:
            user = authenticate(username=username, password=password)
        except Exception as e:
            print(e)
            return self.form_invalid(form)
        #user = authenticate(username=username, password=password)
        print('not perm')

        if user is not None and not user.is_active:
            print('perm')
            raise PermissionDenied("Your account is not activated yet.")
        try:
            return super().form_valid(form)
        except PermissionDenied as e:
            print('ret')
            return self.render_to_response(
                self.get_context_data(form=form, permission_denied=str(e))
            )
        #return super().form_valid(form)

    def get_success_url(self):
        user = self.request.user
        if user.is_staff:
            return reverse_lazy('about')
        else:
            return reverse_lazy('summarize')


class TokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        toka=six.text_type(user.pk)
        print('toka',toka)
        tokb=six.text_type(timestamp)
        print('tokb',tokb)
        tokc=six.text_type(user.is_active)
        print('tokc',tokc)
        tok=toka+tokb+tokc
        print('tok',tok)

        return (tok)


generate_token = TokenGenerator()

class ActivateView(View):
    def get(self, request, uidb64, token):
        try:
            uid = int(urlsafe_base64_decode(uidb64))
            print('uidaaa',uid)
            user = User.objects.get(pk=uid)
            print('useraaa',user)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
            print('none')

        if user is not None and generate_token.check_token(user, token):
            user.is_active = True
            print('aqyui')
            user.save()
            login(request, user)
            return redirect('summarize/?activated=True')
        return render(request, 'account_activation_invalid.html')


class RegisterView(View):
    def get(self, request):
        form = RegistrationForm()
        return render(request, 'register.html', {'form': form})

    def post(self, request):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            if User.objects.filter(username=username).exists():
                form.add_error('username', 'This username is already taken')
                return render(request, 'register.html', {'form': form})

            email = form.cleaned_data.get('email')
            password1 = form.cleaned_data.get('password1')
            password2 = form.cleaned_data.get('password2')

            if password1 and password2 and password1 != password2:
                form.add_error(None, "Passwords don't match")
                return render(request, 'register.html', {'form': form})

            user = User.objects.create_user(username=username, email=email, password=password1)
            user.is_active = False
            user.save()

            current_site = get_current_site(request)
            mail_subject = 'Activate your account.'
            print('user.pk',user.pk)
            uid=urlsafe_base64_encode(force_bytes(user.pk))
            token=generate_token.make_token(user)
            print('uid1',uid)
            print('token1',token)
            message = render_to_string('acc_active_email.html', {
                'user': user,
                'domain': current_site.domain,
                'uid': uid,#urlsafe_base64_encode(force_bytes(user.pk)).decode(),
                'token': token,
            })
            to_email = email
            email = EmailMessage(mail_subject, message, to=[to_email])
            email.content_subtype = "html"

            email.send()

            return redirect('account_activation_sent')

        return render(request, 'register.html', {'form': form})


def logout_view(request):
    logout(request)
    # Redirect the user to the login page or any other page of your choice
    return redirect('login')

def summarize(request):
    if request.method == 'POST':
        arxiv_id = request.POST['arxiv_id']
        arxiv_id = arxiv_id.strip()

        pattern = re.compile(r'^\d{4}\.\d{4,5}(v\d+)?$')
        if not pattern.match(arxiv_id):
            # Return an error message if the format is incorrect
            return render(request, 'summarizer/home.html', {'error': 'Invalid arXiv ID format. It should be a four-digit number, a dot, a four or five-digit number, and an optional version number consisting of the letter "v" and one or more digits. For example, 2101.1234, 2101.12345, and 2101.12345v2 are valid identifiers.'})

        return HttpResponseRedirect(reverse('arxividpage', args=(arxiv_id,)))

    activated = request.GET.get('activated', False)

    return render(request, 'summarizer/home.html', {'activated':activated})

def legal(request):
    stuff_for_frontend = {}

    return render(request, "summarizer/legal-notice.html", stuff_for_frontend)

def about(request):
    stuff_for_frontend = {}

    return render(request, "summarizer/about.html", stuff_for_frontend)

def faq(request):
    stuff_for_frontend = {}

    return render(request, "summarizer/faq.html", stuff_for_frontend)


def contact(request):
    stuff_for_frontend = {}

    if request.method == 'POST':
        name = request.POST['name']
        email = request.POST['email']
        message = request.POST['message']

        # Send an email to the specified email address
        subject = 'Paper Summarization Contact Form: ' + name
        emailto = ['carbonfreeconf@gmail.com']
        #emailto.append(email)
        emailsend = EmailMessage(
            subject,
            message+' From:'+email,
            'SummarizePaper <communication@summarizepaper.com>',  # from
            emailto,  # to
            # getemails,  # bcc
            # reply_to=replylist,
            headers={'Message-From': 'www.summarizepaper.com'},
        )
        #emailsend.content_subtype = "html"

        sent=emailsend.send(fail_silently=False)

        if sent == 1:
            stuff_for_frontend.update({'sent':1})
        else:
            stuff_for_frontend.update({'sent':0})

            print('Failed to send the email.')

        return render(request, 'summarizer/contact.html',stuff_for_frontend)


    return render(request, "summarizer/contact.html", stuff_for_frontend)

def privacy(request):
    stuff_for_frontend = {}

    return render(request, "summarizer/privacy.html", stuff_for_frontend)

def escape_latex(abstract):
    while "$" in abstract:
        start = abstract.index("$")
        end = abstract.index("$", start + 1)
        abstract = abstract[:start] + "\[" + abstract[start + 1:end] + "\]" + abstract[end + 1:]
    return abstract

def arxividpage(request, arxiv_id, error_message=None):
    arxiv_id = arxiv_id.strip()
    if 'ON_HEROKU' in os.environ:
        onhero=True
    else:
        onhero=False


    stuff_for_frontend = {"arxiv_id": arxiv_id,"onhero":onhero}


    pattern = re.compile(r'^\d{4}\.\d{4,5}(v\d+)?$')
    if not pattern.match(arxiv_id):
        print('not')
        errormess='Wrong url. '+arxiv_id+' is an invalid arXiv ID format. It should be a four-digit number, a dot, a four or five-digit number, and an optional version number consisting of the letter "v" and one or more digits. For example, 2101.1234, 2101.12345, and 2101.12345v2 are valid identifiers.'
        # Return an error message if the format is incorrect
        #return render(request, 'summarizer/home.html', {'error': 'Invalid arXiv ID format. It should be a four-digit number, a dot, a four or five-digit number, and an optional version number consisting of the letter "v" and one or more digits. For example, 2101.1234, 2101.12345, and 2101.12345v2 are valid identifiers.'})
        stuff_for_frontend.update({
            'errormess':errormess,
        })
        return render(request, "summarizer/arxividpage.html", stuff_for_frontend)

    page_running = cache.get("ar_"+arxiv_id)
    print('page_running',page_running)
    if page_running:
        print('in page_running')
        # Page is already running, do not start it again
        stuff_for_frontend.update({
            'run2':True,
        })
        return render(request, "summarizer/arxividpage.html", stuff_for_frontend)


    lang = get_language()
    print('lang',lang)
    #if lang =='fr':
    if error_message:
        print('rrr',error_message)
        if error_message=="vote":
            if lang =='fr':
                error_message="Vous avez déjà voté"
            else:
                error_message="You have already voted"

        else:
            error_message=""

        stuff_for_frontend.update({
            'error_message':error_message,
        })

    if request.method == 'POST':
        print('in here')
        if 'run_button' in request.POST:
            print('ok run')
            if ArxivPaper.objects.filter(arxiv_id=arxiv_id).exists():
                print('deja')
                paper=ArxivPaper.objects.filter(arxiv_id=arxiv_id)[0]
            #paper = get_object_or_404(ArxivPaper, arxiv_id=arxiv_id)
            #client_ip = request.META['REMOTE_ADDR']
            #print('clientip',client_ip)
            # Check if this IP address has already voted on this post
                previous_votes = Vote.objects.filter(paper=paper)

                if previous_votes.exists():
                    #we cancel the votes because we rerun the process
                    print('rerun cancel votes')
                    for pv in previous_votes:
                        pv.active=False
                        pv.save()
                    paper.total_votes = 0
                    paper.save()

            stuff_for_frontend.update({
                'run':True,
            })
        return render(request, "summarizer/arxividpage.html", stuff_for_frontend)
    else:
        if ArxivPaper.objects.filter(arxiv_id=arxiv_id).exists():
            print('deja')
            paper=ArxivPaper.objects.filter(arxiv_id=arxiv_id)[0]
            alpaper=True
            print('paper',paper.abstract)
            #updated = timezone.make_aware(paper.updated)
            #if paper.updated >= (timezone.now() - timezone.timedelta(minutes=1)):
            if paper.updated >= (timezone.now() - timezone.timedelta(days=365)):
                toolong=False

                # code to run if the paper was updated in the last year
                print('1 days a')

            else:
                toolong=True
                # code to run if the paper was not updated in the last year
                print('1 days b')

            url = paper.license
            cc_format=''
            license = ''
            if url != '' and url != None:
                parts = url.split('/')
                print('parts',parts)
                license = parts[-3]
                version = parts[-2]
                if license.upper() != "NONEXCLUSIVE-DISTRIB":
                    cc_format = 'CC ' + license.upper() + ' ' + version
                else:
                    cc_format = license.upper() + ' ' + version

            public=False
            #print('lo',license.upper())
            if (license.upper().strip() == "BY" or license.upper().strip() == "BY-SA" or license.upper().strip() == "BY-NC-SA" or license.upper().strip() == "ZERO"):
                public=True
                print('pub')

            print('cc',cc_format) # Output: CC BY-NC-SA 4.0

            #paper.abstract = escape_latex(paper.abstract)
            if (paper.notes is not None) and (paper.notes != "") and (paper.notes != "['']"):
                print('nnnnnnoooottees',paper.notes)
                try:
                    notes = ast.literal_eval(paper.notes)
                except ValueError:
                    # Handle the error by returning a response with an error message to the user
                    return HttpResponse("Invalid input: 'notes' attribute is not a valid Python literal.")

                #notes=ast.literal_eval(paper.notes)
            else:
                notes=''

            stuff_for_frontend.update({
                'paper':paper,
                'notes':notes,
                'cc_format':cc_format,
                'toolong':toolong,
                'public':public,
            })
        else:
            print('nope')
            alpaper=False
            arxiv_detailsf=utils.get_arxiv_metadata(arxiv_id)
            exist=arxiv_detailsf[0]
            #exist, authors, affiliation, link_hp, title, link_doi, abstract, cat, updated, published, journal_ref, comments
            if arxiv_detailsf[0] == 0:
                stuff_for_frontend.update({
                    'exist':exist,
                })
            else:


                arxiv_details=arxiv_detailsf[1:]

                #[authors, affiliation, link_hp, title, link_doi, abstract, cat, updated, published_datetime, journal_ref, comments]
                keys = ['authors', 'affiliation', 'link_homepage', 'title', 'link_doi', 'abstract', 'category', 'updated', 'published_arxiv', 'journal_ref', 'comments', 'license']

                arxiv_dict = dict(zip(keys, arxiv_details))
                print('jfgh',arxiv_detailsf)
                published_datetime = datetime.strptime(arxiv_dict['published_arxiv'], '%Y-%m-%dT%H:%M:%SZ')

                arxiv_dict['published_arxiv']=published_datetime

                url = arxiv_dict['license']
                cc_format=''
                if url != '':
                    parts = url.split('/')
                    print('parts',parts)
                    license = parts[-3]
                    version = parts[-2]
                    if license.upper() != "NONEXCLUSIVE-DISTRIB":
                        cc_format = 'CC ' + license.upper() + ' ' + version
                    else:
                        cc_format = license.upper() + ' ' + version

                print(cc_format) # Output: CC BY-NC-SA 4.0

                stuff_for_frontend.update({
                    'exist':exist,
                    'details':arxiv_dict,
                    'cc_format':cc_format
                })

        stuff_for_frontend.update({
            'alpaper':alpaper,
        })

        return render(request, "summarizer/arxividpage.html", stuff_for_frontend)


def vote(request, paper_id, direction):
    print('in there')
    paper = get_object_or_404(ArxivPaper, arxiv_id=paper_id)
    client_ip = request.META['REMOTE_ADDR']
    print('clientip',client_ip)
    # Check if this IP address has already voted on this post

    previous_votes = Vote.objects.filter(paper=paper, ip_address=client_ip)
    if previous_votes.exists() and not client_ip=='127.0.0.1':
        print('exist vote')

        error_message = 'vote#totvote'
        #error_message = urllib.parse.quote(error_message)
        #print('tturleee',error_message)
        url = '/arxiv-id/' + paper_id + '/' + error_message
        #print('tturl',url)
        return redirect(url)

        #return redirect('arxividpage', arxiv_id=paper_id, error_message=error_message)#%2523=#
        #return redirect('post_detail', post_id=post.pk)

    # Create a new vote
    if direction=="up":
        valuevote=1
    elif direction=="down":
        valuevote=-1
    else:
        valuevote=0

    if valuevote != 0:
        vote = Vote(paper=paper, ip_address=client_ip, vote=valuevote)
        vote.save()
        #if paper.total_votes+valuevote>=0:
        paper.total_votes += valuevote
        paper.save()

    return redirect('arxividpage', arxiv_id=paper_id)


def update_cache(request):
    arxiv_id = request.GET.get('arxiv_id')
    arxiv_group_name = "ar_%s" % arxiv_id
    cache.set(arxiv_group_name, False)
    return HttpResponse("Cache updated")
