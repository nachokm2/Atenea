/// Qué fotograma pintar, dada una [FiguraDelMundo] y cuánto se avanzó.
///
/// El fotograma de marcha se elige por **distancia recorrida**, nunca por la
/// fase libre de un reloj: el desplazamiento del caminante en el sendero usa
/// `Curves.easeInOutCubic` (el cuerpo frena al acercarse al destino), y con
/// una fase de tiempo lineal las piernas seguirían a ritmo constante
/// mientras el cuerpo desacelera — patina. Distanciándolo del reloj, el
/// fotograma cambia exactamente al mismo ritmo que el cuerpo se mueve, se
/// acelere o frene como se acelere o frene.
///
/// El reposo (en las paradas, sin desplazamiento) sí es libre en el tiempo:
/// ahí no hay nada que sincronizar con una distancia que no existe.
library;

import 'figura_del_mundo.dart';

/// Fotogramas por ciclo de marcha: contacto-izq, paso, contacto-der, paso.
const int fotogramasDeMarcha = 4;

/// Fotogramas de reposo: de pie, y el mismo un poco más bajo (como al
/// exhalar) — el "bob" que `06c-inventario-equipamiento-tienda.md` planeó
/// para el avatar detallado y nunca se construyó, aquí gratis y horneado en
/// el arte en vez de animado en tiempo de ejecución.
const int fotogramasDeReposo = 2;

/// Cuánto avanza la figura, en dp del lienzo del sendero, por cada fotograma
/// de marcha. Es una medida del arte (cuánto se desplaza el pie dibujado
/// entre una pose de contacto y la siguiente), no una preferencia de ritmo:
/// se ajusta con el arte real en la Fase D/E; hasta entonces, un valor
/// razonable para una figura de ~120dp de alto.
const double dpPorFotogramaDeMarcha = 30;

/// Rutas de fotogramas y props para una [FiguraDelMundo] — puro, sin
/// `BuildContext`: solo arma nombres de archivo con la convención acordada
/// (`docs/planes/mundo-caminable.md`), nunca decide si el archivo existe.
class CicloDeMarcha {
  const CicloDeMarcha(this.figura);

  final FiguraDelMundo figura;

  // `.name`, no `.api`: las carpetas de arte ya existentes usan español
  // (`assets/arte/capas/masculino/`), nunca el valor inglés de la API.
  String get _carpeta => 'assets/arte/mundo/${figura.familia}/${figura.arquetipo.name}';

  /// Ruta del fotograma de marcha `indice` (se envuelve sobre
  /// [fotogramasDeMarcha]; nunca lanza por un índice fuera de rango).
  String rutaDeMarcha(int indice) =>
      '$_carpeta/marcha_${_dosDigitos(indice % fotogramasDeMarcha)}.webp';

  /// Ruta del fotograma de reposo `indice` (envuelto sobre [fotogramasDeReposo]).
  String rutaDeReposo(int indice) =>
      '$_carpeta/reposo_${_dosDigitos(indice % fotogramasDeReposo)}.webp';

  /// Prop en la mano diestra, o `null` si no hay nada que dibujar ahí — el
  /// caminante no inventa un arma que el aprendiz no tiene equipada.
  String? get rutaDePropDiestro =>
      figura.claseArma == null ? null : 'assets/arte/mundo/props/${figura.claseArma!.api}.webp';

  /// Prop en la mano zurda, o `null`.
  String? get rutaDePropZurdo => figura.claseSecundaria == null
      ? null
      : 'assets/arte/mundo/props/${figura.claseSecundaria!.api}.webp';

  /// Fotograma de marcha que toca a esta distancia (en dp, siempre desde el
  /// origen del tramo — nunca negativa en la práctica, pero `abs()` por si
  /// una animación invertida la pasara así). Cíclico: pasado el último
  /// fotograma, vuelve al primero, como cualquier ciclo de marcha real.
  int fotogramaPorDistancia(double dp) {
    final int paso = (dp.abs() / dpPorFotogramaDeMarcha).floor();
    return paso % fotogramasDeMarcha;
  }

  /// Fotograma de reposo que toca en la fase `fase01` (`0..1`, típicamente
  /// `AnimationController.value` en `repeat()`) — envuelve sola cualquier
  /// valor fuera de `[0,1)`, así que un controlador que pase de `1.0` no
  /// revienta el índice.
  int fotogramaDeReposoPorFase(double fase01) {
    final double envuelta = fase01 - fase01.floorToDouble();
    final int indice = (envuelta * fotogramasDeReposo).floor();
    return indice.clamp(0, fotogramasDeReposo - 1);
  }
}

String _dosDigitos(int n) => n.toString().padLeft(2, '0');
