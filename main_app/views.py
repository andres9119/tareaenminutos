from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from .models import BlogPost, ContactMessage, ChatMessage
from .models import Banner
from .forms import ContactForm, ChatForm

def index(request):
    """Vista de la landing page pública"""
    blog_posts = BlogPost.objects.filter(published=True)[:3]
    banner = Banner.objects.filter(active=True).first()
    context = {
        'recent_posts': blog_posts
        , 'banner': banner
    }
    return render(request, 'main_app/index.html', context)

def login_view(request):
    """Vista de login restringido para usuarios específicos"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Redirigir según el rol del usuario
            if user.is_superuser or user.groups.filter(name='Administrador').exists():
                return redirect('dashboard_admin')
            elif user.groups.filter(name='Tutor').exists():
                return redirect('dashboard_tutor')
            else:
                return redirect('bienvenidos')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
    
    return render(request, 'main_app/login.html')

def logout_view(request):
    """Vista para cerrar sesión"""
    logout(request)
    return redirect('index')

@login_required(login_url='login')
def administracion(request):
    """Vista de administración restringida solo para usuarios autenticados"""
    return render(request, 'main_app/administracion.html')


@login_required(login_url='login')
def bienvenidos(request):
    """Página de bienvenida simple después del login"""
    return render(request, 'main_app/bienvenidos.html')

def blog_list(request):
    """Lista de posts del blog"""
    posts = BlogPost.objects.filter(published=True)
    context = {
        'posts': posts
    }
    return render(request, 'main_app/blog_list.html', context)

def blog_detail(request, slug):
    """Detalle de un post del blog"""
    post = get_object_or_404(BlogPost, slug=slug, published=True)
    context = {
        'post': post
    }
    return render(request, 'main_app/blog_detail.html', context)

def contact_view(request):
    """Vista de formulario de contacto"""
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tu mensaje ha sido enviado correctamente. Nos pondremos en contacto pronto.')
            return redirect('index')
    else:
        form = ContactForm()
    
    context = {
        'form': form
    }
    return render(request, 'main_app/contact.html', context)


from django.http import HttpResponse
from accounts.decorators import admin_required
from .models import ContactMessage


@admin_required
def contact_mensajes_list(request):
    mensajes = ContactMessage.objects.all().order_by('-created_at')
    return render(request, 'private/contacto/mensajes_list.html', {'mensajes': mensajes})


@admin_required
def contact_mensaje_detalle(request, pk):
    mensaje = get_object_or_404(ContactMessage, pk=pk)
    if not mensaje.read:
        mensaje.read = True
        mensaje.save(update_fields=['read'])
    return render(request, 'private/contacto/mensaje_detalle.html', {'m': mensaje})


@login_required(login_url='login')
def chat_view(request):
    """Vista del chat interno"""
    messages_list = ChatMessage.objects.filter(user=request.user)
    
    if request.method == 'POST':
        form = ChatForm(request.POST)
        if form.is_valid():
            chat_message = form.save(commit=False)
            chat_message.user = request.user
            chat_message.save()
            return redirect('chat')
    else:
        form = ChatForm()
    
    context = {
        'messages': messages_list,
        'form': form
    }
    return render(request, 'main_app/chat.html', context)


def sitemap_view(request):
    """Genera el sitemap.xml del sitio"""
    posts = BlogPost.objects.filter(published=True)
    base_url = settings.SITE_BASE_URL.rstrip('/')
    
    urls = [
        {'loc': base_url, 'priority': '1.0', 'changefreq': 'weekly'},
        {'loc': f'{base_url}/blog/', 'priority': '0.8', 'changefreq': 'weekly'},
        {'loc': f'{base_url}/contacto/', 'priority': '0.7', 'changefreq': 'monthly'},
    ]
    
    for post in posts:
        urls.append({
            'loc': f'{base_url}/blog/{post.slug}/',
            'priority': '0.6',
            'changefreq': 'monthly',
            'lastmod': post.updated_at.strftime('%Y-%m-%d') if post.updated_at else '',
        })
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += '  <url>\n'
        xml += f'    <loc>{u["loc"]}</loc>\n'
        xml += f'    <priority>{u["priority"]}</priority>\n'
        xml += f'    <changefreq>{u["changefreq"]}</changefreq>\n'
        if u.get('lastmod'):
            xml += f'    <lastmod>{u["lastmod"]}</lastmod>\n'
        xml += '  </url>\n'
    xml += '</urlset>'
    
    return HttpResponse(xml, content_type='application/xml')
