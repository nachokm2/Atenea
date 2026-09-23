/// Qué figura y qué prop empuñado le corresponden a un aprendiz en el mundo
/// caminable — nunca un dato inventado en el cliente.
///
/// La familia (masculino/femenino) sale de la misma regla que ya usa el
/// avatar detallado (`Arte.claveDeFigura`), para que el mundo y el Vestidor
/// jamás discrepen sobre qué figura le toca a alguien. La clase de lo
/// empuñado sale de `CapaAvatar.claseArma`, que el servidor ya resolvió
/// (`docs/planes/mundo-caminable.md`, Fase 0) — este archivo no mantiene, y
/// no debe mantener nunca, una tabla de código de ítem a clase: eso es
/// exactamente lo que se decidió evitar para no exigir un release de la app
/// por cada arma nueva del catálogo.
library;

import '../../../datos/dtos.dart';
import '../../../design/arte.dart';

/// La figura simplificada que le corresponde a un aprendiz, y lo que lleva
/// en cada mano — todo derivado de datos reales, nunca supuesto.
class FiguraDelMundo {
  const FiguraDelMundo({
    required this.familia,
    required this.arquetipo,
    this.claseArma,
    this.claseSecundaria,
  });

  /// `'masculino'` o `'femenino'` — la misma familia del avatar detallado.
  final String familia;

  /// La Orden del personaje.
  final Arquetipo arquetipo;

  /// Lo que lleva en la mano diestra (`RanuraItem.arma`), o `null`.
  final ClaseDeArma? claseArma;

  /// Lo que lleva en la mano zurda (`RanuraItem.secundaria`), o `null`.
  final ClaseDeArma? claseSecundaria;
}

/// Deriva la [FiguraDelMundo] de un aprendiz a partir de su avatar real.
FiguraDelMundo figuraDelMundo({
  required List<CapaAvatar> capas,
  required RasgosAvatar rasgos,
  required Arquetipo arquetipo,
}) {
  final String figura = Arte.claveDeFigura(
    trato: rasgos.formaTrato,
    cuerpo: rasgos.tipoCuerpo,
    rostro: rasgos.rostro,
  );
  return FiguraDelMundo(
    familia: Arte.familiaDe(figura),
    arquetipo: arquetipo,
    claseArma: _claseEquipadaEn(capas, RanuraItem.arma),
    claseSecundaria: _claseEquipadaEn(capas, RanuraItem.secundaria),
  );
}

/// La clase de la primera capa de [ranura] que traiga una — un ítem puede
/// aportar varias capas (z distintos) y todas comparten la misma clase, así
/// que la primera que la traiga alcanza.
ClaseDeArma? _claseEquipadaEn(List<CapaAvatar> capas, RanuraItem ranura) {
  for (final CapaAvatar capa in capas) {
    if (capa.ranura == ranura && capa.claseArma != null) return capa.claseArma;
  }
  return null;
}
