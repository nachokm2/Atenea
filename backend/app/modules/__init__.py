"""Módulos de negocio del monolito modular de Atenea (CONTRACT.md §1.3).

Siete paquetes con límites explícitos y una dirección de dependencias fija:

``identity`` ← ``content`` ← ``ingestion`` / ``ai``, y ``progress`` → ``gamification`` → ``economy``.

La comunicación entre módulos en tiempo de ejecución se hace por eventos de
dominio (``gamification.eventos.registrar_evento``), no importando servicios
ajenos, salvo donde el contrato lo autoriza explícitamente.
"""
