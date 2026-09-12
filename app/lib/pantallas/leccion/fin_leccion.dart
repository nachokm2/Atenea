/// P10 — Fin de lección.
///
/// Cierra la lección con el desglose del `RewardsReceipt` (§7.10) y entrega el
/// recibo a la [ColaCelebraciones], que se encarga de los overlays de racha,
/// subida de nivel e ítem (máximo tres, §5.3). Todo lo demás queda como chips
/// en esta misma pantalla.
library;

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/celebraciones.dart';
import '../../estado/leccion.dart';
import '../../navegacion/rutas.dart';
import 'widgets/desglose_recompensas.dart';

/// Resumen de recompensas de la lección recién completada.
class PantallaFinLeccion extends StatefulWidget {
  const PantallaFinLeccion({super.key, this.leccionId});

  /// Lección cerrada, cuando se llega por la ruta `/leccion/{id}/resumen`.
  final String? leccionId;

  @override
  State<PantallaFinLeccion> createState() => _PantallaFinLeccionState();
}

class _PantallaFinLeccionState extends State<PantallaFinLeccion> {
  bool _encolado = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) => _encolar());
  }

  void _encolar() {
    if (_encolado || !mounted) return;
    final ReciboRecompensas? recibo =
        context.read<ControladorLeccion>().recibo;
    if (recibo == null) return;
    _encolado = true;
    context.read<ColaCelebraciones>().encolar(recibo);
  }

  void _salir(String destino) {
    context.read<ColaCelebraciones>().vaciar();
    context.go(destino);
  }

  @override
  Widget build(BuildContext context) {
    final ControladorLeccion control = context.watch<ControladorLeccion>();
    final ColaCelebraciones cola = context.watch<ColaCelebraciones>();
    final ReciboRecompensas? recibo = control.recibo;

    if (recibo == null) {
      return PantallaAtenea(
        cuerpo: EstadoVacio(
          icono: Icons.emoji_events_outlined,
          titulo: 'Aquí no hay nada que celebrar todavía',
          mensaje:
              'Termina una lección y volveremos con tus recompensas en la mano.',
          textoAccion: 'Volver al Inicio',
          alTocarAccion: () => _salir(Rutas.inicio),
        ),
      );
    }

    final AteneaPalette p = context.paleta;
    final Leccion? leccion = control.leccion;
    final String titulo = leccion?.titulo ?? 'Actividad completada';
    final String? rutaId = leccion?.rutaId;
    final int respuestas = control.pasos
        .where((PasoLeccion paso) => paso.esPregunta)
        .length;

    return PantallaAtenea(
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        Espacio.md,
        Espacio.md,
        Espacio.md,
      ),
      piePersistente: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          BotonPrimario(
            texto: 'Continuar',
            icono: Icons.arrow_forward_rounded,
            subtitulo: rutaId == null ? null : (leccion?.tituloRuta ?? 'Tu Ruta'),
            alTocar: () =>
                _salir(rutaId == null ? Rutas.inicio : Rutas.ruta(rutaId)),
          ),
          TextButton(
            onPressed: () => _salir(Rutas.inicio),
            child: const Text('Volver al Inicio'),
          ),
        ],
      ),
      cuerpo: ListView(
        children: <Widget>[
          _Corona(titulo: titulo, esRepaso: control.esRepaso),
          const SizedBox(height: Espacio.lg),
          DesgloseRecompensas(recibo: recibo, respuestas: respuestas),
          const SizedBox(height: Espacio.sm),
          BarraNivel(nivel: recibo.nivel, xpTotal: recibo.xp?.totalDespues),
          if (recibo.objetivoDiario != null) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            _ObjetivoDeHoy(objetivo: recibo.objetivoDiario!),
          ],
          if (cola.chips.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.md),
            ChipsCelebracion(chips: cola.chips),
          ],
          if (recibo.desbloqueos.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            ListaDesbloqueos(desbloqueos: recibo.desbloqueos),
          ],
          if (recibo.sincronizacionPendiente) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            const AvisoSincronizacion(),
          ],
          const SizedBox(height: Espacio.md),
          Center(
            child: Text(
              control.esRepaso
                  ? 'Lo que se repasa, se queda.'
                  : 'Un paso más en tu Ruta. El Reino lo anota.',
              textAlign: TextAlign.center,
              style: context.textos.bodyMedium?.copyWith(
                color: p.textoSecundario,
                fontStyle: FontStyle.italic,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Corona de cierre: destello, título y nombre de la lección.
class _Corona extends StatelessWidget {
  const _Corona({required this.titulo, required this.esRepaso});

  final String titulo;
  final bool esRepaso;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool quieto = reducirMovimiento(context);

    final Widget emblema = Container(
      width: 116,
      height: 116,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: p.oro.withValues(alpha: 0.14),
        border: Border.all(color: p.oro, width: 2),
        boxShadow: quieto ? null : Sombra.brillo(p.oro, 18),
      ),
      child: Icon(
        esRepaso ? Icons.refresh_rounded : Icons.workspace_premium_rounded,
        size: 58,
        color: p.oro,
      ),
    );

    return Column(
      children: <Widget>[
        Semantics(
          label: esRepaso ? 'Repaso completado' : 'Lección completada',
          child: ExcludeSemantics(
            child: quieto
                ? emblema
                : emblema
                    .animate()
                    .scale(
                      begin: const Offset(0.8, 0.8),
                      end: const Offset(1, 1),
                      duration: Movimiento.transicion,
                      curve: Movimiento.entrada,
                    )
                    .shimmer(
                      duration: Movimiento.celebracion,
                      color: p.oro.withValues(alpha: 0.5),
                    ),
          ),
        ),
        const SizedBox(height: Espacio.md),
        Text(
          esRepaso ? 'REPASO COMPLETADO' : 'LECCIÓN COMPLETADA',
          textAlign: TextAlign.center,
          style: context.textos.labelSmall?.copyWith(color: p.textoSecundario),
        ),
        const SizedBox(height: Espacio.xxs),
        Text(
          titulo,
          textAlign: TextAlign.center,
          style: context.textos.displaySmall,
        ),
      ],
    );
  }
}

/// Estado del objetivo diario tras la actividad.
class _ObjetivoDeHoy extends StatelessWidget {
  const _ObjetivoDeHoy({required this.objetivo});

  final ObjetivoDiario objetivo;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool cumplido = objetivo.cumplido;
    return TarjetaAtenea(
      colorBorde: cumplido ? p.exito : null,
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(
                cumplido
                    ? Icons.task_alt_rounded
                    : Icons.flag_circle_outlined,
                size: 20,
                color: cumplido ? p.exito : p.arcano,
              ),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Text(
                  cumplido ? 'Objetivo de hoy cumplido' : 'Objetivo de hoy',
                  style: context.textos.titleMedium,
                ),
              ),
              if (cumplido && objetivo.oroBonus > 0)
                Text(
                  '+${objetivo.oroBonus} Oro',
                  style: Cifras.pequena(context).copyWith(color: p.oro),
                ),
            ],
          ),
          const SizedBox(height: Espacio.xs),
          BarraProgreso(
            valor: objetivo.fraccion,
            color: cumplido ? p.exito : p.arcano,
            etiqueta: objetivo.metaLegible,
            textoDerecha: '${objetivo.progreso}/${objetivo.meta}',
          ),
        ],
      ),
    );
  }
}
