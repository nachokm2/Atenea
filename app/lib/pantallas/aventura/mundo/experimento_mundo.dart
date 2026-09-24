/// Fase 0a/C — el experimento descartable del sendero caminable.
///
/// Pregunta que responde, y solo esa (Fase C): ¿un serpenteante vertical con
/// 4-10 paradas se siente como un mundo con ALGO que de verdad camina, o el
/// problema nunca fue el disco de color de la Fase 0a? El caminante ya es
/// `CaminanteEnSenda` (reposo/marcha reales, ancla en los pies), pero
/// pintado con `PintorDeCaminanteDeMentira` — sin un solo pixel de arte
/// generado, a propósito: eso es la Fase D, y depende de que este
/// experimento valide primero que vale la pena seguir gastando.
///
/// Vive fuera del árbol de producción a propósito, enlazado solo desde
/// Ajustes → Herramientas del Reino (`kDebugMode`), para poder borrarlo
/// entero sin dejar rastro si la respuesta es "no". Ver
/// `docs/planes/mundo-caminable.md` para las preguntas de salida completas.
library;

import 'package:flutter/material.dart';

import '../../../datos/dtos.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import '../widgets/nodos_mapa.dart' show EstiloNodo, colorDeNodo;
import 'caminante.dart';
import 'ciclo_marcha.dart';
import 'figura_del_mundo.dart';
import 'pintor_senda.dart';
import 'senda.dart';
import 'terreno.dart';

/// Figura de ejemplo para el spike — no hay avatar real que leer aquí, igual
/// que `_detalleDeEjemplo` fabrica una Ruta de ejemplo más abajo.
const FiguraDelMundo _figuraDeEjemplo =
    FiguraDelMundo(familia: 'masculino', arquetipo: Arquetipo.acero);

// Rodrigo, en el teléfono, sobre el arreglo de las piernas: "muy rapido aun".
// La causa real no era el espejo de piernas: `_control` animaba CUALQUIER
// tramo —uno corto o uno larguísimo— en la misma `Movimiento.corta` (250ms)
// fija, pensada para un salto de color arbitrario en la Fase 0a, no para un
// personaje con un ciclo de marcha real. A velocidad constante en vez de
// duración fija: cada fotograma de marcha dura lo mismo en pantalla sin
// importar cuánto mida el tramo, y con 250ms ni un tramo corto alcanzaba a
// mostrar cada pose el tiempo suficiente para leerse como zancada.
const double _msPorFotogramaDeMarcha = 150;
const double _dpPorSegundo = dpPorFotogramaDeMarcha / _msPorFotogramaDeMarcha * 1000;
const int _duracionMinimaMs = 300;
const int _duracionMaximaMs = 4000;

/// Pantalla del experimento: monta un sendero de ejemplo y deja caminar.
class PantallaExperimentoMundo extends StatefulWidget {
  const PantallaExperimentoMundo({super.key});

  @override
  State<PantallaExperimentoMundo> createState() =>
      _PantallaExperimentoMundoState();
}

class _PantallaExperimentoMundoState extends State<PantallaExperimentoMundo>
    with SingleTickerProviderStateMixin {
  late AnimationController _control;

  // `null`: todavía no hubo ningún toque, el caminante descansa donde esté
  // `_paradaActual` — `build()` resuelve el punto real ahí mismo.
  Offset? _origen;
  Offset? _destino;

  int _cantidadDeModulos = 6;
  int _paradaActual = 0;
  String? _aviso;

  @override
  void initState() {
    super.initState();
    // La duración real se recalcula en cada toque, según la distancia
    // (`_duracionDelTramo`) — este valor inicial nunca se usa para animar.
    _control = AnimationController(vsync: this, duration: const Duration(milliseconds: _duracionMinimaMs));
    // Sin esto, al llegar el caminante queda congelado en el último
    // fotograma de marcha para siempre: nada más fuerza una reconstrucción
    // de esta pantalla solo porque el controlador terminó de animar, y
    // `origen`/`destino` sin reconstruir siguen siendo el tramo recorrido,
    // no el punto de reposo.
    _control.addStatusListener((AnimationStatus estado) {
      if (estado == AnimationStatus.completed) setState(() {});
    });
  }

  @override
  void dispose() {
    _control.dispose();
    super.dispose();
  }

  DetalleRuta get _detalle => _detalleDeEjemplo(_cantidadDeModulos);

  // La misma curva que ya usaba la animación de posición: el cuerpo frena al
  // llegar, y por eso `CicloDeMarcha.fotogramaPorDistancia` —que lee este
  // mismo progreso— nunca puede leer la fase lineal del reloj.
  Animation<double> get _avance =>
      CurvedAnimation(parent: _control, curve: Curves.easeInOutCubic);

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    // Con la animación ya terminada (o sin haber arrancado nunca), el
    // caminante descansa en el punto real de la parada — nunca se queda
    // congelado en el último fotograma del tramo que ya recorrió.
    final bool enMovimiento = _control.isAnimating;

    return PantallaAtenea(
      titulo: 'Spike · sendero caminable',
      mostrarVolver: true,
      padding: EdgeInsets.zero,
      limitarAnchoLectura: false,
      cuerpo: Column(
        children: <Widget>[
          _Controles(
            cantidad: _cantidadDeModulos,
            alCambiar: (int n) => setState(() {
              _cantidadDeModulos = n;
              _paradaActual = 0;
              _origen = null;
              _destino = null;
              _control.value = 0;
            }),
          ),
          if (_aviso != null)
            Container(
              width: double.infinity,
              color: p.info.withValues(alpha: 0.15),
              padding: const EdgeInsets.all(Espacio.sm),
              child: Text(_aviso!, style: context.textos.bodySmall),
            ),
          Expanded(
            // `LayoutBuilder`, no un ancho fijo a mano: la pantalla no limita
            // el ancho de lectura (`limitarAnchoLectura: false`) ni pone
            // padding, así que el mundo real mide el ancho del dispositivo,
            // no 360 — con un trazo de 6px la diferencia era invisible, pero
            // el terreno ilustrado necesita el ancho real para no
            // desalinearse del sendero.
            child: LayoutBuilder(
              builder: (BuildContext context, BoxConstraints c) {
                final Senda senda = Senda.desdeDetalle(_detalle, ancho: c.maxWidth);
                final Offset enReposo = senda.centroDeParada(_paradaActual) ?? Offset.zero;
                return senda.estaVacia
                    ? const Center(child: Text('Sin módulos de ejemplo'))
                    : _Mundo(
                        senda: senda,
                        origen: enMovimiento ? (_origen ?? enReposo) : enReposo,
                        destino: enMovimiento ? (_destino ?? enReposo) : enReposo,
                        avance: _avance,
                        alTocarParada: (int indice) => _tocarParada(indice, senda),
                      );
              },
            ),
          ),
        ],
      ),
    );
  }

  // `senda` la pasa quien la dibujó (`LayoutBuilder` en `build()`), no se
  // reconstruye acá con un ancho a mano — dos fuentes de verdad sobre el
  // mismo ancho son exactamente el bug que esto reemplaza.
  void _tocarParada(int indice, Senda senda) {
    ParadaSenda? destino;
    for (final ParadaSenda p in senda.paradas) {
      if (p.indice == indice) {
        destino = p;
        break;
      }
    }
    if (destino == null) return;
    final ParadaSenda paradaDestino = destino;

    final bool alcanzable = indice <= senda.ultimaAlcanzable;
    final int indiceFinal = alcanzable ? indice : senda.ultimaAlcanzable + 1;
    final Offset? origen = senda.centroDeParada(_paradaActual);
    final Offset fin = alcanzable
        ? paradaDestino.centro
        : (senda.portonAntesDe(indiceFinal)?.centro ?? paradaDestino.centro);
    if (origen == null) return;

    setState(() {
      _aviso = alcanzable
          ? null
          : (paradaDestino.modulo?.motivoBloqueo ??
              'Completa el módulo anterior para pasar por aquí.');
      _origen = origen;
      _destino = fin;
      _paradaActual = alcanzable ? indice : _paradaActual;
    });
    _control
      ..duration = _duracionDelTramo(origen, fin)
      ..reset()
      ..forward();
  }

  /// A velocidad constante, no a duración fija: un tramo largo tarda más que
  /// uno corto, o el personaje "teletransporta" en vez de caminar.
  static Duration _duracionDelTramo(Offset origen, Offset destino) {
    final double distancia = (destino - origen).distance;
    final int ms = (distancia / _dpPorSegundo * 1000).round();
    return Duration(milliseconds: ms.clamp(_duracionMinimaMs, _duracionMaximaMs));
  }
}

class _Controles extends StatelessWidget {
  const _Controles({required this.cantidad, required this.alCambiar});

  final int cantidad;
  final ValueChanged<int> alCambiar;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(Espacio.sm),
      child: Row(
        children: <Widget>[
          Text('Módulos de ejemplo: $cantidad', style: context.textos.bodyMedium),
          Expanded(
            child: Slider(
              value: cantidad.toDouble(),
              min: 2,
              max: 10,
              divisions: 8,
              label: '$cantidad',
              onChanged: (double v) => alCambiar(v.round()),
            ),
          ),
        ],
      ),
    );
  }
}

/// La cámara (scroll vertical) + el lienzo del sendero + las paradas tocables
/// + el caminante.
class _Mundo extends StatefulWidget {
  const _Mundo({
    required this.senda,
    required this.origen,
    required this.destino,
    required this.avance,
    required this.alTocarParada,
  });

  final Senda senda;
  final Offset origen;
  final Offset destino;
  final Animation<double> avance;
  final ValueChanged<int> alTocarParada;

  @override
  State<_Mundo> createState() => _MundoState();
}

class _MundoState extends State<_Mundo> {
  final ScrollController _camara = ScrollController();

  @override
  void initState() {
    super.initState();
    // `widget.avance` envuelve siempre el mismo `AnimationController` de la
    // pantalla (nunca se recrea), así que escuchar esta única instancia
    // alcanza para toda la vida del widget — no hace falta perseguir
    // instancias nuevas en `didUpdateWidget`.
    widget.avance.addListener(_seguirConLaCamara);
  }

  void _seguirConLaCamara() {
    if (!_camara.hasClients) return;
    final Offset pos = Offset.lerp(widget.origen, widget.destino, widget.avance.value)!;
    final double objetivo =
        (pos.dy - _camara.position.viewportDimension * 0.45)
            .clamp(0, _camara.position.maxScrollExtent);
    _camara.jumpTo(objetivo);
  }

  @override
  void dispose() {
    widget.avance.removeListener(_seguirConLaCamara);
    _camara.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final Senda senda = widget.senda;
    return SingleChildScrollView(
      controller: _camara,
      child: SizedBox(
        width: senda.tamano.width,
        height: senda.tamano.height,
        child: Stack(
          children: <Widget>[
            // Detrás de todo: el terreno ilustrado (Parte A, "el camino son
            // solo flechas, podemos hacerlo más un reino"). Sin arte real
            // todavía (Fase T1) — cae sola a `colorDeSuelo` vía `errorBuilder`.
            Positioned.fill(child: TerrenoDelMundo(tamano: senda.tamano)),
            Positioned.fill(
              child: CustomPaint(painter: pintorDeSenda(context, senda)),
            ),
            for (final ParadaSenda parada in senda.paradas)
              Positioned(
                left: parada.centro.dx - 28,
                top: parada.centro.dy - 28,
                child: _ParadaSpike(
                  key: ValueKey<String>('parada-${parada.indice}'),
                  parada: parada,
                  onTap: () => widget.alTocarParada(parada.indice),
                ),
              ),
            CaminanteEnSenda(
              key: const ValueKey<String>('caminante'),
              ciclo: CicloDeMarcha(_figuraDeEjemplo),
              origen: widget.origen,
              destino: widget.destino,
              avance: widget.avance,
              alto: 80,
            ),
          ],
        ),
      ),
    );
  }
}

/// Ancho y alto de la estructura ilustrada que se compone DETRÁS del círculo
/// (Fase E, a pedido de Rodrigo viendo el terreno ya wireado: "me agrada el
/// fondo, podemos agregar castillos o algo donde llega el personaje?").
///
/// 140dp de alto es el techo que ya validamos contra `pasoDeParada` (240dp,
/// `senda.dart`): dos estructuras consecutivas, ancladas cada una por su
/// BASE en su propia parada (igual que `CaminanteEnSenda` ancla en los
/// pies, no en el centro), quedan con 100dp de aire entre la base de la de
/// arriba y el techo de la de abajo (240 − 140) — aun en el peor caso, sin
/// aprovechar el serpenteo horizontal del sendero (`puntoEnY`), que en la
/// práctica separa aún más a la mayoría de los pares consecutivos. Más
/// angosta que alta (112dp) para no acercarse al borde del mundo cuando la
/// pantalla es tan angosta como `_anchoMinimo` (320dp, `senda.dart`).
///
/// Nota para la Fase de arte real: `margenSenda` (96dp, `senda.dart`) es
/// MENOR que este alto — la estructura de la parada 0 se recorta ~44dp
/// contra el borde superior del mundo. Inocuo por ahora (ese borde no se ve:
/// la cámara arranca centrada en la parada actual, no en el tope del
/// mundo) pero si se nota al pulir, la corrección es `margenSenda` ≥
/// `_altoEstructura`, no achicar la estructura de todas las demás paradas.
const double _anchoEstructura = 112;
const double _altoEstructura = 140;

/// Qué archivo de estructura ilustrada le corresponde a cada `EstiloNodo` —
/// mismo patrón que `_iconoDeReino`, y a propósito un `switch` sobre el
/// enum y no un `Map<EstiloNodo, String>`: con el `switch`, si mañana se
/// agrega un caso a `EstiloNodo` y esta función no se actualiza, el
/// análisis estático de Dart lo marca como error de compilación — con un
/// `Map` esa omisión compila igual y el estado nuevo se queda sin arte en
/// silencio hasta que alguien lo note a ojo. El tesoro no es un caso más de
/// este switch: es un `TipoParada` aparte, resuelto en `_ParadaSpike` con
/// `_rutaDeEstructuraDelTesoro`, igual que ya hace `_iconoDeReino` con
/// `Icons.emoji_events_rounded` en vez de leer este switch para el tesoro.
///
/// Sin arte real todavía (fase de scaffolding, antes de gastar en arte):
/// estos seis archivos (los 5 de acá + el del tesoro) no existen ni están
/// declarados en `pubspec.yaml`, así que las seis paradas caen solas, vía
/// el `errorBuilder` de `Image.asset`, a `SizedBox.shrink()` — a diferencia
/// de `Caminante`/`TerrenoDelMundo`, acá la caída no necesita pintar un
/// placeholder propio: el círculo con su ícono, detrás del cual se compone
/// esta estructura, ya es la vista completa.
String _rutaDeEstructura(EstiloNodo estilo) => switch (estilo) {
      EstiloNodo.completado => 'assets/arte/mundo/estructuras/completado.webp',
      EstiloNodo.actual => 'assets/arte/mundo/estructuras/actual.webp',
      EstiloNodo.disponible => 'assets/arte/mundo/estructuras/disponible.webp',
      EstiloNodo.bloqueado => 'assets/arte/mundo/estructuras/bloqueado.webp',
      EstiloNodo.enConstruccion =>
        'assets/arte/mundo/estructuras/en_construccion.webp',
    };

/// La estructura del tesoro final — deliberadamente su propio archivo, no
/// el de `EstiloNodo.bloqueado`/`completado` que el tesoro también podría
/// tener (ver `Senda.desdeDetalle`: el tesoro usa esos mismos dos estilos
/// para SU color, mientras la Ruta no está completa/completa). Un cofre o
/// portón final se lee distinto de un castillo bloqueado a mitad de camino,
/// igual que el tesoro ya usa `Icons.emoji_events_rounded` en vez de
/// `_iconoDeReino(estilo)`.
const String _rutaDeEstructuraDelTesoro =
    'assets/arte/mundo/estructuras/tesoro.webp';

class _ParadaSpike extends StatelessWidget {
  const _ParadaSpike({required this.parada, required this.onTap, super.key});

  final ParadaSenda parada;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final Color color = colorDeNodo(context, parada.estilo);
    final String rutaEstructura = parada.tipo == TipoParada.tesoro
        ? _rutaDeEstructuraDelTesoro
        : _rutaDeEstructura(parada.estilo);

    // La caja de layout sigue siendo 56×56: el `Positioned` que la ubica en
    // `_MundoState.build()` (`parada.centro - 28`) no cambia una línea, así
    // que el círculo tocable tampoco se mueve un pixel — sigue siendo
    // exactamente el mismo punto donde el usuario ya espera tocar. La
    // estructura se compone DETRÁS del círculo y se pinta POR FUERA de esta
    // caja (`Stack.clipBehavior: Clip.none`); agrandar la caja misma, en vez
    // de dejarla desbordar, movería ese punto de anclaje del toque.
    return SizedBox(
      width: 56,
      height: 56,
      child: Stack(
        clipBehavior: Clip.none,
        children: <Widget>[
          // Detrás y más grande: ancla su BASE en el mismo punto de sendero
          // que el círculo — igual que el caminante ancla en los pies, no
          // en el centro (`CaminanteEnSenda`, `caminante.dart`): una
          // estructura como un castillo "pisa" el punto del sendero con su
          // base, no flota centrada sobre él.
          //
          // `bottom: 28`, no `bottom: 0`: el punto real del sendero
          // (`parada.centro`) está a 28dp del borde inferior de esta caja de
          // 56×56 (su mitad, `56 / 2`) — ahí es donde tiene que pisar la
          // base de la estructura, no en el borde de la caja.
          //
          // Puramente decorativa: `IgnorePointer` + `ExcludeSemantics`, para
          // que el único nodo de accesibilidad y el único que responde al
          // toque siga siendo el círculo de abajo — nunca dos áreas
          // tocables ambiguas para la misma parada.
          Positioned(
            left: (56 - _anchoEstructura) / 2,
            bottom: 28,
            child: IgnorePointer(
              child: ExcludeSemantics(
                child: SizedBox(
                  width: _anchoEstructura,
                  height: _altoEstructura,
                  child: Image.asset(
                    rutaEstructura,
                    fit: BoxFit.contain,
                    alignment: Alignment.bottomCenter,
                    errorBuilder:
                        (BuildContext context, Object error, StackTrace? pila) =>
                            const SizedBox.shrink(),
                  ),
                ),
              ),
            ),
          ),
          Semantics(
            button: true,
            label: parada.tipo == TipoParada.tesoro
                ? 'Tesoro final'
                : (parada.modulo?.nombreVisible ?? 'Módulo ${parada.indice + 1}'),
            child: GestureDetector(
              onTap: onTap,
              child: Container(
                width: 56,
                height: 56,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: color.withValues(alpha: 0.18),
                  border: Border.all(color: color, width: 2),
                ),
                child: Icon(
                  parada.tipo == TipoParada.tesoro
                      ? Icons.emoji_events_rounded
                      : _iconoDeReino(parada.estilo),
                  color: color,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Íconos más "de reino" que los genéricos de producción
/// (`nodos_mapa.dart.iconoDeNodo`: un check, una flecha de "jugar", un
/// candado) — solo para este spike descartable, a pedido de Rodrigo: "el
/// camino son solo flechas, podemos hacerlo más un reino". No toca el mapa
/// real — los aprendices de verdad siguen viendo los íconos de producción
/// hasta que esto se apruebe y se decida si vale la pena llevarlo allá.
IconData _iconoDeReino(EstiloNodo estilo) => switch (estilo) {
      EstiloNodo.completado => Icons.auto_stories_rounded, // un tomo ya conquistado
      EstiloNodo.actual => Icons.hiking_rounded, // acá estás, listo para seguir camino
      EstiloNodo.disponible => Icons.explore_rounded, // un sendero abierto por explorar
      EstiloNodo.bloqueado => Icons.castle_rounded, // el portón del reino, cerrado
      EstiloNodo.enConstruccion => Icons.local_fire_department_rounded, // la forja, aún trabajando
    };

/// Una Ruta de ejemplo con `n` módulos, variando su estilo a propósito: los
/// cinco `EstiloNodo` de una vez (índices 0 a 4: completado, actual,
/// enConstruccion, disponible, bloqueado), y de ahí en más todo bloqueado —
/// para que el experimento muestre los tres colores del trazo (recorrido,
/// pendiente, más allá del candado) Y las seis estructuras ilustradas (Fase
/// E, `_rutaDeEstructura`) sin depender de datos reales.
///
/// El índice 1 llega solo a `EstiloNodo.actual`: `status: 'in_progress'` lo
/// vuelve el primer módulo con `EstadoModulo.enProgreso`, y
/// `DetalleRuta.moduloActual` (`dtos.dart`) devuelve exactamente ese —
/// ningún campo aparte que fijar a mano.
DetalleRuta _detalleDeEjemplo(int n) {
  final List<Map<String, dynamic>> modulos = <Map<String, dynamic>>[];
  for (int i = 0; i < n; i++) {
    final String estado = i == 0
        ? 'completed'
        : (i == 1 ? 'in_progress' : (i <= 3 ? 'available' : 'locked'));
    modulos.add(<String, dynamic>{
      'module_id': 'mod-$i',
      'title': 'Módulo ${i + 1}',
      'position': i + 1,
      'status': estado,
      // Índice 2: "disponible" en `status` (no bloqueado, sigue siendo
      // alcanzable) pero con contenido todavía escribiéndose — la única
      // combinación real que produce `EstiloNodo.enConstruccion`
      // (`estiloDeModulo` la resuelve ANTES que "actual"/"disponible").
      'content_status': i == 2 ? 'generating' : 'ready',
      'lessons_total': 2,
      'lessons_completed': i == 0 ? 2 : 0,
      'mastery': i == 0 ? 82.0 : 0.0,
      'assessment': <String, dynamic>{
        'assessment_id': 'eval-$i',
        'module_id': 'mod-$i',
        'title': 'Prueba del módulo ${i + 1}',
        'question_count': 8,
        'pass_score': 70.0,
        'max_attempts_per_day': 2,
        'content_status': 'ready',
        'attempts_used': 0,
        'best_score': null,
        'passed': i == 0,
        'can_start': i <= 1,
        'cooldown_until': null,
      },
      'locked_reason': i > 3 ? 'Completa el módulo $i para desbloquear' : null,
      'topics': <Map<String, dynamic>>[
        <String, dynamic>{
          'topic_id': 'tema-$i',
          'module_id': 'mod-$i',
          'title': 'Tema $i',
          'position': 1,
          'lessons': <Map<String, dynamic>>[
            <String, dynamic>{
              'lesson_id': 'lec-$i-1',
              'title': 'Lección 1',
              'position': 1,
              'status': i == 0 ? 'completed' : 'not_started',
              'content_status': 'ready',
              'estimated_seconds': 480,
            },
            <String, dynamic>{
              'lesson_id': 'lec-$i-2',
              'title': 'Lección 2',
              'position': 2,
              'status': i == 0 ? 'completed' : 'not_started',
              'content_status': 'ready',
              'estimated_seconds': 480,
            },
          ],
        },
      ],
    });
  }
  return DetalleRuta.desdeJson(<String, dynamic>{
    'path': <String, dynamic>{
      'path_id': 'ruta-spike',
      'title': 'Sendero de ejemplo',
      'status': 'active',
    },
    'status': 'active',
    'modules': modulos,
  });
}
