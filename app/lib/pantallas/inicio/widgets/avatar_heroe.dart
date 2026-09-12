/// Retrato del héroe para la cabecera del Inicio.
///
/// El avatar definitivo se dibuja por capas (§6.4 del documento de UX) a
/// partir del manifiesto `avatar_layers` que envía el panel. Mientras el
/// pipeline de arte no exista, aquí se pinta un medallón con el emblema de la
/// Orden, el anillo de la Orden y un realce dorado cuando el héroe ya lleva
/// equipo puesto. La firma no cambiará cuando lleguen los recursos gráficos.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/tokens.dart';

/// Medallón circular del héroe.
class AvatarHeroe extends StatelessWidget {
  const AvatarHeroe({
    required this.arquetipo,
    super.key,
    this.capas = const <CapaAvatar>[],
    this.nombre = '',
    this.tamano = Espacio.xxl + Espacio.xs,
    this.alTocar,
  });

  /// Orden elegida en la creación del personaje.
  final Arquetipo arquetipo;

  /// Manifiesto de capas del servidor, ya ordenado por z.
  final List<CapaAvatar> capas;

  /// Nombre del héroe, para el lector de pantalla.
  final String nombre;

  /// Diámetro del medallón.
  final double tamano;

  /// Normalmente lleva al Vestidor (P16).
  final VoidCallback? alTocar;

  /// ¿Hay al menos una pieza de equipo puesta?
  bool get _llevaEquipo =>
      capas.any((CapaAvatar capa) => capa.ranura != null);

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color anillo = _llevaEquipo ? p.oro : p.arcano;

    final Widget medallon = Container(
      width: tamano,
      height: tamano,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            p.arcano.withValues(alpha: 0.85),
            p.dominio.withValues(alpha: 0.55),
          ],
        ),
        border: Border.all(color: anillo, width: 2),
        boxShadow: Sombra.brillo(anillo, _llevaEquipo ? Espacio.xs : 0),
      ),
      alignment: Alignment.center,
      child: Icon(
        _emblema(arquetipo),
        size: tamano * 0.46,
        color: p.sobreArcano,
      ),
    );

    final String etiqueta = nombre.isEmpty
        ? 'Tu héroe, ${arquetipo.etiqueta}'
        : '$nombre, ${arquetipo.etiqueta}';

    if (alTocar == null) {
      return Semantics(label: etiqueta, image: true, child: medallon);
    }

    return Semantics(
      label: etiqueta,
      button: true,
      child: InkWell(
        onTap: alTocar,
        customBorder: const CircleBorder(),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minWidth: Medida.areaTactilMin,
            minHeight: Medida.areaTactilMin,
          ),
          child: Center(child: ExcludeSemantics(child: medallon)),
        ),
      ),
    );
  }

  static IconData _emblema(Arquetipo orden) => switch (orden) {
        Arquetipo.acero => Icons.shield_rounded,
        Arquetipo.arcano => Icons.auto_awesome_rounded,
        Arquetipo.bosque => Icons.park_rounded,
        Arquetipo.muro => Icons.security_rounded,
        Arquetipo.estandarte => Icons.flag_rounded,
        Arquetipo.corona => Icons.workspace_premium_rounded,
        Arquetipo.runas => Icons.menu_book_rounded,
        Arquetipo.bosqueAntiguo => Icons.forest_rounded,
      };
}
