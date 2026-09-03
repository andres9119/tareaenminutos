from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetView, PasswordResetDoneView,
    PasswordResetConfirmView, PasswordResetCompleteView,
)
from django.contrib import messages
from django.conf import settings
from django.core.paginator import Paginator
from django.urls import reverse, reverse_lazy
from .models import BlogPost, ContactMessage, ChatMessage
from .models import Banner
from .forms import ContactForm, ChatForm, TutorPasswordResetForm, BlogPostForm, BlogBlockFormSet, BlogBlockFormSetLegacy

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


class TutorPasswordResetView(PasswordResetView):
    """Solicitud de recuperación de contraseña (solo tutores)."""
    template_name = 'main_app/recuperar_contrasena.html'
    form_class = TutorPasswordResetForm
    success_url = reverse_lazy('password_reset_done')
    from_email = None


password_reset_request = TutorPasswordResetView.as_view()
password_reset_done = PasswordResetDoneView.as_view(
    template_name='main_app/password_reset_done.html')
password_reset_confirm = PasswordResetConfirmView.as_view(
    template_name='main_app/password_reset_confirm.html',
    success_url=reverse_lazy('password_reset_complete'))
password_reset_complete = PasswordResetCompleteView.as_view(
    template_name='main_app/password_reset_complete.html')

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
            contacto = form.save()
            messages.success(request, 'Tu mensaje ha sido enviado correctamente. Nos pondremos en contacto pronto.')
            _notificar_contacto_a_admins(contacto)
            return redirect('index')
    else:
        form = ContactForm()
    
    context = {
        'form': form
    }
    return render(request, 'main_app/contact.html', context)


def _notificar_contacto_a_admins(contacto):
    """Envía por email a todos los administradores activos un nuevo mensaje de contacto."""
    if not settings.EMAIL_HOST_USER:
        print(f"[TEM] (dev) Nuevo mensaje de contacto sin SMTP:\n{contacto.name} ({contacto.email}) - {contacto.subject}\n{contacto.message}")
        return
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    User = get_user_model()
    admins = User.objects.filter(
        Q(is_superuser=True) | Q(groups__name='Administrador'),
        is_active=True,
    ).exclude(email='').values_list('email', flat=True)
    if not admins:
        return
    from django.core.mail import send_mail
    try:
        send_mail(
            subject=f"Nuevo mensaje de contacto - {contacto.subject}",
            message=(
                f"Has recibido un nuevo mensaje desde el formulario de contacto.\n\n"
                f"Nombre: {contacto.name}\n"
                f"Email: {contacto.email}\n"
                f"Teléfono: {contacto.phone or 'No especificado'}\n"
                f"Recibido: {contacto.created_at.strftime('%d/%m/%Y %H:%M')}\n\n"
                f"Mensaje:\n{contacto.message}\n\n"
                f"---\nTarea en Minutos"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=list(admins),
            fail_silently=False,
        )
    except Exception:
        pass


from django.http import HttpResponse
from accounts.decorators import admin_required
from .models import ContactMessage


@admin_required
def contact_mensajes_list(request):
    mensajes = Paginator(
        ContactMessage.objects.all().order_by('-created_at'), 5
    ).get_page(request.GET.get('page', 1))
    return render(request, 'private/contacto/mensajes_list.html', {
        'mensajes': mensajes,
        'pagina': mensajes,
    })


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


# ─── Admin: Blog (gestión de artículos con bloques de contenido) ──────────────

@admin_required
def blog_admin_list(request):
    """Lista de art�culos del blog para administrar (solo Admin)."""
    posts = Paginator(
        BlogPost.objects.select_related('author').order_by('-created_at'), 5
    ).get_page(request.GET.get('page', 1))
    return render(request, 'private/blog/blog_list.html', {
        'posts': posts,
        'pagina': posts,
    })


def _guardar_blog_post(request, post=None):
    """Lógica común de crear/editar un post del blog con sus bloques.
    Retorna una redirección (HttpResponse) si se guardó, o (form, formset, post)."""
    form = BlogPostForm(request.POST or None, request.FILES or None, instance=post)

    if request.method == 'GET' and post and not post.bloques.exists() and post.content.strip():
        # Artículo antiguo (solo Markdown): se convierte en un bloque de texto
        # editable para que el editor por bloques no lo pierda.
        formset = BlogBlockFormSetLegacy(
            instance=post, prefix='bloques',
            initial=[{'tipo': 'texto', 'contenido': post.content}],
        )
    else:
        formset = BlogBlockFormSet(
            request.POST or None, request.FILES or None,
            instance=post or BlogPost(), prefix='bloques',
        )

    if request.method == 'POST':
        if form.is_valid() and formset.is_valid():
            post_obj = form.save(commit=False)
            post_obj.author = request.user
            post_obj.slug = form.cleaned_data.get('slug') or form.data.get('slug')
            if not post_obj.slug:
                from django.utils.text import slugify
                post_obj.slug = slugify(post_obj.title)[:50]
            post_obj.save()  # asigna pk para poder enlazar los bloques

            for idx, f in enumerate(formset.forms):
                if f.cleaned_data and not f.cleaned_data.get('DELETE'):
                    f.instance.post = post_obj
                    f.instance.orden = idx
                    f.instance.save()

            for f in formset.deleted_forms:
                if f.instance.pk:
                    f.instance.delete()

            # Si por cualquier motivo no hubo bloques salvados y existía contenido
            # Markdown legacy, lo preservamos como bloque de texto.
            if not post_obj.bloques.exists():
                legacy = post.content if post and post.pk else ''
                BlogBlock.objects.create(
                    post=post_obj, tipo='texto',
                    contenido=legacy or '', orden=0,
                )

            action = 'actualizado' if post else 'creado'
            messages.success(request, f'Artículo "{post_obj.title}" {action} correctamente.')
            return redirect('blog_admin_list')

    return form, formset, post

@admin_required
def blog_admin_crear(request):
    """Crear un nuevo artículo del blog (solo Admin)."""
    resultado = _guardar_blog_post(request)
    if isinstance(resultado, HttpResponse):
        return resultado
    form, formset, post = resultado
    return render(request, 'private/blog/blog_editar.html', {
        'form': form, 'formset': formset, 'post': post,
        'titulo_pagina': 'Crear Artículo',
    })


@admin_required
def blog_admin_editar(request, pk):
    """Editar un artículo existente del blog (solo Admin)."""
    post = get_object_or_404(BlogPost, pk=pk)
    resultado = _guardar_blog_post(request, post=post)
    if isinstance(resultado, HttpResponse):
        return resultado
    form, formset, _ = resultado
    return render(request, 'private/blog/blog_editar.html', {
        'form': form, 'formset': formset, 'post': post,
        'titulo_pagina': 'Editar Artículo',
    })


@admin_required
def blog_admin_eliminar(request, pk):
    """Eliminar un artículo del blog definitivamente (solo Admin)."""
    post = get_object_or_404(BlogPost, pk=pk)
    if request.method == 'POST':
        titulo = post.title
        post.delete()
        messages.success(request, f'Artículo "{titulo}" eliminado.')
        return redirect('blog_admin_list')
    return render(request, 'private/blog/blog_eliminar.html', {'post': post})
