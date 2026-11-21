from django.apps import AppConfig


class OcenyConfig(AppConfig):
    name = "oceny"
    verbose_name = "Oceny okresowe"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import sygnaly  # noqa: F401 - rejestruje zapis logowań w dzienniku zdarzeń
