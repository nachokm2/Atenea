/// Geometría pura del sendero de la Ruta (P07): dónde está cada parada y el
/// camino que las une, sin `BuildContext` ni widgets de Flutter.
///
/// Separado de la pantalla por la misma razón que las reglas de estilo de
/// `camino_ruta.dart` viven aparte de ella: para poder probarlo sin montar
/// nada. Este archivo reusa `estiloDeModulo` en vez de reinventar cuándo un
/// módulo está bloqueado — el portón y la parada nunca pueden discrepar sobre
/// eso, porque leen la misma regla.
///
/// **Nunca normaliza por el total de módulos.** Los módulos de una Ruta se
/// generan de a uno (`content/rutas.py._encargar_contenido`) y el total
/// cambia mientras el aprendiz mira la pantalla; una capa que reparta el
/// sendero entre "los N módulos de hoy" reubicaría — y con eso,
/// teletransportaría — cada parada ya visitada en cuanto la forja termine el
/// módulo siguiente. Por eso la posición de la parada `i` es una función de
/// `i` sola, nunca de `i` y del total: crece hacia abajo, nunca se
/// reacomoda.
library;

import 'dart:math' as math;
import 'dart:ui' show Offset, Size;

import '../../../datos/repositorios.dart';
import '../widgets/camino_ruta.dart' show estiloDeModulo;
import '../widgets/nodos_mapa.dart' show EstiloNodo;

/// Distancia vertical entre dos paradas consecutivas.
const double pasoDeParada = 240;

/// Margen antes de la primera parada y después de la última.
const double margenSenda = 96;

/// Ancho mínimo y máximo del serpenteo, antes de aplicar la amplitud.
const double _anchoMinimo = 320;
const double _anchoMaximo = 520;

double _amplitud(double ancho) =>
    (ancho.clamp(_anchoMinimo, _anchoMaximo) - margenSenda) * 0.32;

/// Punto del sendero a una altura `y`, dentro de un mundo de `ancho` dp.
///
/// Curva seno pura: el sendero pasa exactamente por cada parada por
/// construcción (`puntoEnY(yDeParada(i), ancho) == parada(i).centro`), sin
/// necesidad de una curva Bézier ni de calcular longitud de arco.
Offset puntoEnY(double y, double ancho) {
  final double x = ancho / 2 +
      _amplitud(ancho) * math.sin(math.pi * (y - margenSenda) / (2 * pasoDeParada));
  return Offset(x, y);
}

/// Altura de la parada `indice` (0-based).
double yDeParada(int indice) => margenSenda + indice * pasoDeParada;

/// Qué representa una parada del sendero.
enum TipoParada {
  /// Un módulo de la Ruta.
  modulo,

  /// El tesoro final.
  tesoro,
}

/// Una parada del sendero.
class ParadaSenda {
  const ParadaSenda({
    required this.indice,
    required this.centro,
    required this.tipo,
    required this.estilo,
    this.modulo,
  });

  /// Orden dentro del sendero, 0-based. El tesoro tiene `indice == modulos.length`.
  final int indice;

  /// Centro de la parada en el espacio del mundo (antes de aplicar la cámara).
  final Offset centro;

  /// Qué representa.
  final TipoParada tipo;

  /// Cómo se pinta — la misma regla que ya usaba la lista de nodos.
  final EstiloNodo estilo;

  /// El módulo real, cuando `tipo == TipoParada.modulo`.
  final ModuloRuta? modulo;
}

/// El portón entre la parada `indice - 1` y la parada `indice`: la evaluación
/// del módulo anterior. Cerrado si y solo si la parada siguiente está
/// bloqueada — no hay una segunda fuente de verdad sobre el bloqueo.
class PortonSenda {
  const PortonSenda({
    required this.antesDeIndice,
    required this.centro,
    required this.abierto,
  });

  /// El portón está justo antes de esta parada.
  final int antesDeIndice;

  final Offset centro;
  final bool abierto;
}

/// El sendero completo de una Ruta: sus paradas, sus portones y su tamaño.
class Senda {
  const Senda({
    required this.paradas,
    required this.portones,
    required this.tamano,
    required this.ultimaAlcanzable,
  });

  /// Construye el sendero a partir del detalle de la Ruta.
  ///
  /// Determinista: mismo `detalle` y mismo `ancho`, mismo resultado, siempre
  /// — sin `Random` sin sembrar, sin depender del reloj.
  factory Senda.desdeDetalle(DetalleRuta detalle, {required double ancho}) {
    final List<ModuloRuta> modulos = detalle.modulos;
    // Sin módulos no hay sendero que trazar — ni siquiera el tesoro: la
    // pantalla real (`camino_ruta.dart`) tampoco lo pinta hoy, solo el estado
    // vacío. Un sendero de un solo tesoro inalcanzable no sería fiel a eso.
    if (modulos.isEmpty) {
      return Senda(
        paradas: const <ParadaSenda>[],
        portones: const <PortonSenda>[],
        tamano: Size(ancho, margenSenda * 2),
        ultimaAlcanzable: -1,
      );
    }

    final List<ParadaSenda> paradas = <ParadaSenda>[];
    final List<PortonSenda> portones = <PortonSenda>[];
    int ultimaAlcanzable = -1;

    for (int i = 0; i < modulos.length; i++) {
      final ModuloRuta modulo = modulos[i];
      final EstiloNodo estilo = estiloDeModulo(detalle, modulo);
      paradas.add(
        ParadaSenda(
          indice: i,
          centro: puntoEnY(yDeParada(i), ancho),
          tipo: TipoParada.modulo,
          estilo: estilo,
          modulo: modulo,
        ),
      );
      if (estilo != EstiloNodo.bloqueado) ultimaAlcanzable = i;

      if (i > 0) {
        portones.add(
          PortonSenda(
            antesDeIndice: i,
            centro: puntoEnY(yDeParada(i) - pasoDeParada / 2, ancho),
            abierto: estilo != EstiloNodo.bloqueado,
          ),
        );
      }
    }

    final int indiceTesoro = modulos.length;
    final bool rutaCompletada = detalle.ruta.estado == EstadoRuta.completada;
    paradas.add(
      ParadaSenda(
        indice: indiceTesoro,
        centro: puntoEnY(yDeParada(indiceTesoro), ancho),
        tipo: TipoParada.tesoro,
        estilo: rutaCompletada ? EstiloNodo.completado : EstiloNodo.bloqueado,
      ),
    );
    portones.add(
      PortonSenda(
        antesDeIndice: indiceTesoro,
        centro: puntoEnY(yDeParada(indiceTesoro) - pasoDeParada / 2, ancho),
        abierto: rutaCompletada,
      ),
    );
    if (rutaCompletada) ultimaAlcanzable = indiceTesoro;

    return Senda(
      paradas: paradas,
      portones: portones,
      tamano: Size(ancho, yDeParada(indiceTesoro) + margenSenda),
      ultimaAlcanzable: ultimaAlcanzable,
    );
  }

  /// Todas las paradas, en orden (módulos, luego el tesoro).
  final List<ParadaSenda> paradas;

  /// Los portones entre paradas consecutivas.
  final List<PortonSenda> portones;

  /// Tamaño total del mundo, para el `SizedBox` que lo contiene.
  final Size tamano;

  /// Índice de la última parada realmente alcanzable a pie: la primera
  /// bloqueada detiene el camino antes de llegar a ella.
  final int ultimaAlcanzable;

  /// El centro de la parada `indice`, o `null` si no existe.
  Offset? centroDeParada(int indice) {
    for (final ParadaSenda p in paradas) {
      if (p.indice == indice) return p.centro;
    }
    return null;
  }

  /// El portón justo antes de la parada `indice`, o `null` si no hay uno
  /// (la primera parada no tiene portón detrás).
  PortonSenda? portonAntesDe(int indice) {
    for (final PortonSenda p in portones) {
      if (p.antesDeIndice == indice) return p;
    }
    return null;
  }

  /// ¿Hay algo que caminar? (una Ruta sin módulos no tiene sendero).
  bool get estaVacia => paradas.isEmpty;
}
