/// Bandeja de notificaciones: los mensajes que el Reino envía al héroe.
///
/// Se abre como hoja inferior desde la campana del Inicio (§3.3 regla 4), no
/// como pantalla nueva. Cada mensaje lleva a su destino con el traductor de
/// enlaces profundos; al tocarlo se marca leído.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../../data/errores.dart';
import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import '../../../estado/gamificacion.dart';
import '../../../navegacion/armazon.dart';
import '../../../navegacion/rutas.dart';
import 'esqueletos.dart';
import 'formatos.dart';

/// Abre la bandeja y navega al destino del mensaje que se toque.
Future<void> abrirBandejaNotificaciones(BuildContext context) async {
  final GoRouter enrutador = GoRouter.of(context);
  final String? destino = await mostrarHoja<String>(
    context,
    constructor: (BuildContext hoja) => const HojaNotificaciones(),
  );
  if (destino != null && destino.isNotEmpty) enrutador.go(destino);
}

/// Campana con su contador de mensajes sin leer.
class CampanaNotificaciones extends StatelessWidget {
  const CampanaNotificaciones({
    required this.sinLeer,
    required this.alTocar,
    super.key,
  });

  /// Mensajes pendientes de leer.
  final int sinLeer;

  /// Abre la bandeja.
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final String etiqueta = sinLeer == 0
        ? 'Mensajes del Reino, ninguno sin leer'
        : sinLeer == 1
            ? 'Mensajes del Reino, 1 sin leer'
            : 'Mensajes del Reino, $sinLeer sin leer';

    return Semantics(
      button: true,
      label: etiqueta,
      child: ExcludeSemantics(
        child: IconButton(
          tooltip: 'Mensajes del Reino',
          onPressed: alTocar,
          icon: Stack(
            clipBehavior: Clip.none,
            children: <Widget>[
              const Icon(Icons.notifications_none_rounded),
              if (sinLeer > 0)
                Positioned(
                  right: -Espacio.xxs,
                  top: -Espacio.xxs,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: Espacio.xxs),
                    constraints: const BoxConstraints(minWidth: Espacio.md),
                    decoration: BoxDecoration(
                      color: p.brasa,
                      borderRadius: Redondeo.rPildora,
                      border: Border.all(color: p.fondo),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      sinLeer > 9 ? '9+' : '$sinLeer',
                      style: context.textos.labelSmall?.copyWith(
                        color: p.sobreArcano,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Contenido de la hoja: la lista de mensajes.
class HojaNotificaciones extends StatefulWidget {
  const HojaNotificaciones({super.key});

  @override
  State<HojaNotificaciones> createState() => _HojaNotificacionesState();
}

class _HojaNotificacionesState extends State<HojaNotificaciones> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      context.read<ControladorGamificacion>().cargarNotificaciones();
    });
  }

  void _abrir(Notificacion aviso) {
    final ControladorGamificacion gami = context.read<ControladorGamificacion>();
    if (!aviso.estaLeida) {
      unawaited(gami.marcarLeida(aviso.id));
    }
    final String destino =
        EnlacesProfundos.aDireccionInterna(aviso.enlaceProfundo) ?? Rutas.inicio;
    Navigator.of(context).pop(destino);
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final ControladorGamificacion gami = context.watch<ControladorGamificacion>();
    final List<Notificacion> avisos = gami.notificaciones;
    final ErrorAtenea? error = gami.errorNotificaciones;

    return SafeArea(
      top: false,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.82,
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            Espacio.md,
            Espacio.sm,
            Espacio.md,
            Espacio.md,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Center(
                child: Container(
                  width: Espacio.xxl,
                  height: Espacio.xxs,
                  decoration: BoxDecoration(
                    color: p.borde,
                    borderRadius: Redondeo.rPildora,
                  ),
                ),
              ),
              const SizedBox(height: Espacio.sm),
              Row(
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          'Mensajes del Reino',
                          style: context.textos.headlineSmall,
                        ),
                        Text(
                          gami.sinLeer == 0
                              ? 'Estás al día'
                              : '${gami.sinLeer} sin leer',
                          style: context.textos.bodyMedium?.copyWith(
                            color: p.textoSecundario,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (gami.sinLeer > 0)
                    TextButton(
                      onPressed: gami.marcarTodasLeidas,
                      child: const Text('Marcar todas'),
                    ),
                ],
              ),
              const SizedBox(height: Espacio.sm),
              Flexible(child: _cuerpo(context, gami, avisos, error)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _cuerpo(
    BuildContext context,
    ControladorGamificacion gami,
    List<Notificacion> avisos,
    ErrorAtenea? error,
  ) {
    if (gami.cargandoNotificaciones && avisos.isEmpty) {
      return const SingleChildScrollView(
        child: ListaEsqueleto(filas: 4, lineas: 2),
      );
    }
    if (error != null && avisos.isEmpty) {
      return SingleChildScrollView(
        child: EstadoError(
          mensaje: error.mensaje,
          alReintentar: () => gami.cargarNotificaciones(forzar: true),
        ),
      );
    }
    if (avisos.isEmpty) {
      return const SingleChildScrollView(
        child: EstadoVacio(
          icono: Icons.mark_email_read_rounded,
          titulo: 'Sin mensajes por ahora',
          mensaje:
              'Aquí te avisaremos cuando tu ruta esté lista, cuando tu racha '
              'necesite atención y cuando desbloquees algo nuevo.',
        ),
      );
    }

    return ListView.separated(
      shrinkWrap: true,
      padding: EdgeInsets.zero,
      itemCount: avisos.length + (gami.hayMasNotificaciones ? 1 : 0),
      separatorBuilder: (BuildContext context, int i) =>
          const SizedBox(height: Espacio.xs),
      itemBuilder: (BuildContext context, int i) {
        if (i >= avisos.length) {
          return Center(
            child: TextButton(
              onPressed: gami.masNotificaciones,
              child: const Text('Ver mensajes anteriores'),
            ),
          );
        }
        return _FilaNotificacion(
          aviso: avisos[i],
          alTocar: () => _abrir(avisos[i]),
        );
      },
    );
  }
}

class _FilaNotificacion extends StatelessWidget {
  const _FilaNotificacion({required this.aviso, required this.alTocar});

  final Notificacion aviso;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color acento = _color(aviso.tipo, p);
    final DateTime? cuando = aviso.fechaVisible;

    return TarjetaAtenea(
      alTocar: alTocar,
      padding: const EdgeInsets.all(Espacio.sm),
      colorBorde: aviso.estaLeida ? null : acento,
      semantica: '${aviso.titulo}. ${aviso.cuerpo}. '
          '${aviso.estaLeida ? 'Leído' : 'Sin leer'}.',
      hijo: ExcludeSemantics(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Container(
              width: Medida.areaTactilMin - Espacio.sm,
              height: Medida.areaTactilMin - Espacio.sm,
              decoration: BoxDecoration(
                color: acento.withValues(alpha: 0.16),
                shape: BoxShape.circle,
              ),
              alignment: Alignment.center,
              child: Icon(_icono(aviso.tipo), color: acento, size: Tipo.subtitulo),
            ),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          aviso.titulo.isEmpty
                              ? aviso.tipo.etiqueta
                              : aviso.titulo,
                          style: context.textos.titleMedium?.copyWith(
                            fontWeight:
                                aviso.estaLeida ? FontWeight.w600 : FontWeight.w800,
                          ),
                        ),
                      ),
                      if (cuando != null)
                        Text(
                          relativo(cuando),
                          style: context.textos.bodySmall?.copyWith(
                            color: p.textoSecundario,
                          ),
                        ),
                    ],
                  ),
                  if (aviso.cuerpo.isNotEmpty) ...<Widget>[
                    const SizedBox(height: 2),
                    Text(
                      aviso.cuerpo,
                      style: context.textos.bodyMedium?.copyWith(
                        color: p.textoSecundario,
                      ),
                    ),
                  ],
                  if (!aviso.estaLeida) ...<Widget>[
                    const SizedBox(height: Espacio.xs),
                    Pildora(texto: 'Sin leer', icono: Icons.circle, color: acento),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  static IconData _icono(TipoNotificacion tipo) => switch (tipo) {
        TipoNotificacion.rutaLista => Icons.map_rounded,
        TipoNotificacion.generacionFallida => Icons.report_problem_rounded,
        TipoNotificacion.recordatorioRacha ||
        TipoNotificacion.ultimaLlamada ||
        TipoNotificacion.hitoCercano =>
          Icons.local_fire_department_rounded,
        TipoNotificacion.misionDiaria => Icons.flag_rounded,
        TipoNotificacion.repasoRecomendado => Icons.psychology_rounded,
        TipoNotificacion.reactivacion => Icons.waving_hand_rounded,
        TipoNotificacion.itemDesbloqueado => Icons.checkroom_rounded,
        TipoNotificacion.logroDesbloqueado => Icons.military_tech_rounded,
        TipoNotificacion.sistema => Icons.notifications_rounded,
      };

  static Color _color(TipoNotificacion tipo, AteneaPalette p) => switch (tipo) {
        TipoNotificacion.rutaLista => p.arcano,
        TipoNotificacion.generacionFallida => p.advertencia,
        TipoNotificacion.recordatorioRacha ||
        TipoNotificacion.ultimaLlamada ||
        TipoNotificacion.hitoCercano =>
          p.brasa,
        TipoNotificacion.misionDiaria => p.exito,
        TipoNotificacion.repasoRecomendado => p.dominio,
        TipoNotificacion.reactivacion => p.info,
        TipoNotificacion.itemDesbloqueado ||
        TipoNotificacion.logroDesbloqueado =>
          p.oro,
        TipoNotificacion.sistema => p.info,
      };
}
