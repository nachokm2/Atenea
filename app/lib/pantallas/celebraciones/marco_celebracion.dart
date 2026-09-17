/// Marco común de los overlays de celebración (P13, P14 y racha).
///
/// Garantías que se cumplen aquí, y no en cada modal:
///
/// - Ninguna celebración retiene al usuario más de 2,4 s: la
///   [ColaCelebraciones] libera [ColaCelebraciones.listaParaContinuar] pasado
///   ese tiempo y el CTA queda activo.
/// - Un toque en cualquier parte salta la animación; si ya terminó, cierra.
/// - Con movimiento reducido no hay destello ni escala: la tarjeta nace en su
///   estado final y las cifras se pintan ya completas.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/celebraciones.dart';

/// Tarjeta a pantalla completa sobre un velo oscuro.
class MarcoCelebracion extends StatelessWidget {
  const MarcoCelebracion({
    required this.acento,
    required this.semantica,
    required this.contenido,
    required this.acciones,
    super.key,
    this.brillo = 0,
    this.hapticaFuerte = false,
  });

  /// Color que manda en el borde, el resplandor y el rótulo.
  final Color acento;

  /// Texto que lee el lector de pantalla al aparecer.
  final String semantica;

  /// Cuerpo de la celebración.
  final Widget contenido;

  /// Botonera inferior.
  final List<Widget> acciones;

  /// Radio del resplandor (rareza). Cero: sin brillo.
  final double brillo;

  /// Vibración media en subida de nivel e ítem; ninguna en errores.
  final bool hapticaFuerte;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final ColaCelebraciones cola = context.watch<ColaCelebraciones>();
    final bool quieto = reducirMovimiento(context);

    // Esta vibración colgaba de `quieto`, o sea del interruptor equivocado:
    // «Reducir animaciones» la apagaba y «Vibración» no la tocaba. Ahora
    // pregunta a quien debe.
    //
    // La decisión se toma aquí y no dentro de la llamada aplazada porque para
    // entonces el `context` puede estar desmontado: la celebración se cierra
    // sola. Por eso tampoco pasa por `Tacto`, que exige un `context` vivo.
    if (hapticaFuerte && hapticaActiva(context)) {
      WidgetsBinding.instance.addPostFrameCallback((Duration _) {
        HapticFeedback.mediumImpact();
      });
    }

    final Widget tarjeta = TarjetaAtenea(
      elevada: true,
      colorBorde: acento,
      brillo: quieto ? 0 : brillo,
      padding: const EdgeInsets.all(Espacio.lg),
      hijo: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          contenido,
          const SizedBox(height: Espacio.lg),
          ...acciones,
        ],
      ),
    );

    final Widget conOrnamentos = Stack(
      children: <Widget>[
        tarjeta,
        Positioned(
          top: Espacio.xs,
          left: Espacio.xs,
          child: OrnamentoEsquina(color: acento),
        ),
        Positioned(
          top: Espacio.xs,
          right: Espacio.xs,
          child: Transform.rotate(
            angle: 1.5708,
            child: OrnamentoEsquina(color: acento),
          ),
        ),
      ],
    );

    return Semantics(
      liveRegion: true,
      label: semantica,
      child: Material(
        color: p.fondo.withValues(alpha: 0.94),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: cola.listaParaContinuar ? cola.descartar : cola.saltarAnimacion,
          child: SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(Espacio.lg),
                child: ConstrainedBox(
                  constraints:
                      const BoxConstraints(maxWidth: Medida.lecturaMax),
                  child: quieto
                      ? conOrnamentos
                      : TweenAnimationBuilder<double>(
                          tween: Tween<double>(begin: 0, end: 1),
                          duration: Movimiento.transicion,
                          curve: Movimiento.entrada,
                          builder: (
                            BuildContext contexto,
                            double t,
                            Widget? hijo,
                          ) =>
                              Opacity(
                            opacity: t.clamp(0, 1).toDouble(),
                            child: Transform.scale(
                              scale: 0.88 + 0.12 * t,
                              child: hijo,
                            ),
                          ),
                          child: conOrnamentos,
                        ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Rótulo pequeño en versalitas sobre el titular de la celebración.
class RotuloCelebracion extends StatelessWidget {
  const RotuloCelebracion({required this.texto, required this.color, super.key});

  /// Texto corto ("NUEVO EQUIPAMIENTO", "SUBISTE DE NIVEL").
  final String texto;

  /// Color de acento de la celebración.
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Text(
      texto.toUpperCase(),
      textAlign: TextAlign.center,
      style: context.textos.labelSmall?.copyWith(color: color),
    );
  }
}
