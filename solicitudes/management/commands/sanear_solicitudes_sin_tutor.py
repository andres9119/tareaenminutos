from django.core.management.base import BaseCommand

from solicitudes.utils import reponer_activas_sin_tutor


class Command(BaseCommand):
    help = (
        'Corrige solicitudes activas sin tutor asignado (huérfanas por '
        'eliminación de tutor): las devuelve a En Cotización con historial.'
    )

    def handle(self, *args, **options):
        saneados = reponer_activas_sin_tutor()
        if not saneados:
            self.stdout.write(self.style.SUCCESS('Sin solicitudes activas huérfanas. OK.'))
            return
        for codigo in saneados:
            self.stdout.write(f'  {codigo} -> En Cotización (saneada)')
        self.stdout.write(
            self.style.SUCCESS(f'{len(saneados)} solicitud(es) saneada(s).')
        )