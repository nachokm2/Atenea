/// Marcadores temporales de pantalla.
///
/// Las 22 pantallas del MVP todavía no existen: este andamio permite que el
/// enrutador compile y que la navegación se pueda recorrer de punta a punta.
/// Cada ruta del enrutador lleva un `// TODO(pantalla): P0X` con el nombre
/// exacto de la clase que debe sustituir a [PantallaEnConstruccion] y el
/// archivo donde vivirá.
library;

import 'package:flutter/material.dart';

import '../design/components.dart';
import '../design/tokens.dart';

/// Andamio de una pantalla que todavía no se ha construido.
class PantallaEnConstruccion extends StatelessWidget {
  const PantallaEnConstruccion({
    required this.codigo,
    required this.titulo,
    super.key,
    this.proposito,
    this.inmersiva = false,
    this.claseEsperada,
  });

  /// Identificador de la pantalla en el documento de UX (`P04`).
  final String codigo;

  /// Nombre visible de la pantalla ("Inicio").
  final String titulo;

  /// Qué resolverá cuando exista.
  final String? proposito;

  /// Los flujos inmersivos se cierran con una X, no con la flecha de volver.
  final bool inmersiva;

  /// Clase definitiva que ocupará este lugar, para dejarlo por escrito.
  final String? claseEsperada;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return PantallaAtenea(
      titulo: titulo,
      mostrarVolver: !inmersiva,
      cerrarEnLugarDeVolver: inmersiva,
      cuerpo: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          EstadoVacio(
            icono: Icons.construction_rounded,
            titulo: '$codigo · $titulo',
            mensaje: proposito ??
                'Esta parte del Reino todavía se está levantando. Vuelve pronto.',
          ),
          if (claseEsperada != null) ...<Widget>[
            const SizedBox(height: Espacio.lg),
            Center(
              child: Pildora(
                texto: claseEsperada!,
                icono: Icons.widgets_outlined,
                color: paleta.textoSecundario,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
