/// Tarjeta "Continúa tu aventura" del Inicio (P04).
///
/// Es la pieza que responde "¿qué hago ahora?" en un segundo: una sola
/// actividad concreta, su miga de pan, su duración y la recompensa que el
/// servidor anuncia. Cuando todavía no hay ninguna Ruta, se transforma en la
/// invitación a empezar la primera aventura.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';

/// Llamada principal del panel.
class TarjetaContinuar extends StatelessWidget {
  const TarjetaContinuar({
    required this.accion,
    required this.alContinuar,
    required this.alCrearRuta,
    required this.alExplorar,
    super.key,
    this.sinRutas = false,
  });

  /// Qué propone el servidor (`continue_action`).
  final AccionContinuar accion;

  /// El héroe todavía no tiene ninguna Ruta propia.
  final bool sinRutas;

  /// Ejecuta la acción propuesta.
  final VoidCallback alContinuar;

  /// Abre P05.
  final VoidCallback alCrearRuta;

  /// Abre P22, las Rutas del Reino.
  final VoidCallback alExplorar;

  bool get _esInvitacion =>
      sinRutas ||
      !accion.hayAlgoQueHacer ||
      accion.tipo == TipoAccionContinuar.crearRuta;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final RecompensaSimple? premio = accion.vistaPreviaRecompensa;

    return TarjetaAtenea(
      elevada: true,
      colorBorde: p.arcano,
      brillo: reducirMovimiento(context) ? 0 : Rareza.raro.brillo,
      padding: const EdgeInsets.all(Espacio.md),
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            _esInvitacion ? 'TU PRIMERA AVENTURA' : 'CONTINÚA TU AVENTURA',
            style: context.textos.labelMedium?.copyWith(
              color: p.textoSecundario,
              letterSpacing: 1.2,
            ),
          ),
          const SizedBox(height: Espacio.sm),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Container(
                width: Medida.areaTactilMin,
                height: Medida.areaTactilMin,
                decoration: BoxDecoration(
                  color: p.arcano.withValues(alpha: 0.16),
                  borderRadius: Redondeo.rBoton,
                  border: Border.all(color: p.arcano.withValues(alpha: 0.5)),
                ),
                alignment: Alignment.center,
                child: Icon(
                  _icono(accion.tipo, _esInvitacion),
                  color: p.arcano,
                  size: Tipo.titulo,
                ),
              ),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      _esInvitacion
                          ? 'Empieza tu primera aventura'
                          : (accion.titulo ?? accion.tipo.etiqueta),
                      style: context.textos.headlineSmall,
                    ),
                    if (!_esInvitacion && accion.migaDePan != null) ...<Widget>[
                      const SizedBox(height: Espacio.xxs),
                      Text(
                        accion.migaDePan!,
                        style: context.textos.bodyMedium?.copyWith(
                          color: p.textoSecundario,
                        ),
                      ),
                    ],
                    if (_esInvitacion) ...<Widget>[
                      const SizedBox(height: Espacio.xxs),
                      Text(
                        'Elige una Ruta del Reino o construye la tuya con tu '
                        'propio material.',
                        style: context.textos.bodyMedium?.copyWith(
                          color: p.textoSecundario,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
          if (!_esInvitacion) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            Wrap(
              spacing: Espacio.xs,
              runSpacing: Espacio.xs,
              children: <Widget>[
                if (accion.minutosEstimados > 0)
                  Pildora(
                    texto: '${accion.minutosEstimados} min',
                    icono: Icons.hourglass_bottom_rounded,
                  ),
                if (premio != null && !premio.estaVacia)
                  Pildora(
                    texto: premio.resumen,
                    icono: Icons.auto_awesome_rounded,
                    color: p.oro,
                  ),
              ],
            ),
          ],
          const SizedBox(height: Espacio.md),
          if (_esInvitacion) ...<Widget>[
            BotonPrimario(
              texto: 'Crear mi ruta',
              icono: Icons.add_road_rounded,
              alTocar: alCrearRuta,
            ),
            const SizedBox(height: Espacio.xs),
            TextButton.icon(
              onPressed: alExplorar,
              icon: const Icon(Icons.explore_rounded),
              label: const Text('Explorar las Rutas del Reino'),
            ),
          ] else
            BotonPrimario(
              texto: accion.tipo.etiqueta,
              subtitulo: premio == null || premio.estaVacia ? null : premio.resumen,
              icono: Icons.play_arrow_rounded,
              alTocar: alContinuar,
            ),
        ],
      ),
    );
  }

  static IconData _icono(TipoAccionContinuar tipo, bool invitacion) {
    if (invitacion) return Icons.auto_stories_rounded;
    return switch (tipo) {
      TipoAccionContinuar.leccion => Icons.menu_book_rounded,
      TipoAccionContinuar.evaluacion => Icons.shield_rounded,
      TipoAccionContinuar.repaso => Icons.refresh_rounded,
      TipoAccionContinuar.practica => Icons.psychology_rounded,
      TipoAccionContinuar.crearRuta => Icons.add_road_rounded,
      TipoAccionContinuar.verGeneracion => Icons.construction_rounded,
      TipoAccionContinuar.ninguna => Icons.explore_rounded,
    };
  }
}
