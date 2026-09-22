/// P13 — Modal de subida de nivel.
///
/// Celebra el hito en menos de 2,5 s y dice qué habilita. Si la acción cruzó
/// varios niveles de golpe, se muestra solo el salto ("Nivel 2 → 4"), como
/// manda la ficha de la pantalla.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/celebraciones.dart';
import '../../navegacion/rutas.dart';
import 'marco_celebracion.dart';

/// Overlay de subida de nivel.
class ModalSubidaDeNivel extends StatelessWidget {
  const ModalSubidaDeNivel({required this.celebracion, super.key});

  /// Celebración que la cola dejó al frente.
  final Celebracion celebracion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final NivelRecibo? nivel = celebracion.nivel;
    final ColaCelebraciones cola = context.watch<ColaCelebraciones>();
    final bool quieto = reducirMovimiento(context);

    final int despues = nivel?.despues ?? 0;
    // Si la acción cruzó varios niveles se anuncia solo el salto completo.
    final String salto = nivel == null || nivel.despues - nivel.antes <= 1
        ? ''
        : 'Nivel ${nivel.antes} → ${nivel.despues}';
    final bool cambioRango = nivel?.cambioRango ?? false;
    // Con cambio de rango se anuncia el salto de rango, no solo el vigente:
    // cruzar a un rango nuevo es un hito propio y merece su propio texto,
    // no el mismo que ascender de nivel dentro del mismo rango.
    final String rango = cambioRango &&
            (nivel?.tituloRangoAntes ?? '').isNotEmpty
        ? '${nivel!.tituloRangoAntes} → ${nivel.tituloRangoDespues}'
        : nivel?.tituloRangoDespues ?? '';
    final int nuevasRarezas = nivel?.rarezasDesbloqueadas.length ?? 0;
    final int oroBonusRango = nivel?.oroBonusRango ?? 0;

    return MarcoCelebracion(
      acento: p.arcano,
      brillo: 14,
      hapticaFuerte: true,
      semantica: celebracion.semantica,
      contenido: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Center(
            child: Container(
              width: 108,
              height: 108,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: p.arcano.withValues(alpha: 0.16),
                border: Border.all(color: p.arcano, width: 2),
                boxShadow: quieto ? null : Sombra.brillo(p.arcano, 16),
              ),
              child: Icon(Icons.shield_rounded, size: 54, color: p.arcano),
            ),
          ),
          const SizedBox(height: Espacio.md),
          RotuloCelebracion(
            texto: cambioRango ? '¡Nuevo rango!' : 'Subiste de nivel',
            color: p.textoSecundario,
          ),
          const SizedBox(height: Espacio.xxs),
          Center(
            child: salto.isNotEmpty
                ? Text(
                    salto,
                    textAlign: TextAlign.center,
                    style: context.textos.displayMedium,
                  )
                : Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: <Widget>[
                      Text('Nivel ', style: context.textos.displaySmall),
                      CifraAnimada(
                        valor: despues,
                        estilo: Cifras.heroe(context).copyWith(color: p.arcano),
                        duracion: Movimiento.corta,
                      ),
                    ],
                  ),
          ),
          if (rango.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.xxs),
            Text(
              rango,
              textAlign: TextAlign.center,
              style: context.textos.headlineSmall?.copyWith(color: p.oro),
            ),
          ],
          if (nivel != null) ...<Widget>[
            const SizedBox(height: Espacio.md),
            BarraProgreso(
              valor: nivel.fraccion,
              color: p.oro,
              etiqueta: 'Camino al nivel ${nivel.despues + 1}',
              textoDerecha: nivel.xpParaSiguiente > 0
                  ? '${nivel.xpParaSiguiente} XP'
                  : null,
            ),
          ],
          if ((nivel?.oroBonus ?? 0) > 0 ||
              oroBonusRango > 0 ||
              nuevasRarezas > 0) ...<Widget>[
            const SizedBox(height: Espacio.md),
            Wrap(
              alignment: WrapAlignment.center,
              spacing: Espacio.xs,
              runSpacing: Espacio.xs,
              children: <Widget>[
                if ((nivel?.oroBonus ?? 0) > 0)
                  Pildora(
                    texto: '+${nivel!.oroBonus} de oro',
                    icono: Medallon.oro.icono,
                    color: p.oro,
                  ),
                if (oroBonusRango > 0)
                  Pildora(
                    texto: '+$oroBonusRango de oro por el rango',
                    icono: Icons.military_tech_rounded,
                    color: p.oro,
                  ),
                if (nuevasRarezas > 0)
                  Pildora(
                    texto: nuevasRarezas == 1
                        ? 'Nueva rareza en el Mercado'
                        : '$nuevasRarezas rarezas nuevas en el Mercado',
                    icono: Icons.storefront_rounded,
                    color: p.arcano,
                  ),
              ],
            ),
          ],
        ],
      ),
      acciones: <Widget>[
        BotonPrimario(
          texto: celebracion.textoAccion,
          alTocar: cola.descartar,
        ),
        if (nuevasRarezas > 0)
          TextButton(
            onPressed: () {
              cola.descartar();
              context.go(Rutas.mercado);
            },
            child: const Text('Ver el Mercado'),
          ),
      ],
    );
  }
}
