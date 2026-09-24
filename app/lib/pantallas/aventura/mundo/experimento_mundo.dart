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

class _ParadaSpike extends StatelessWidget {
  const _ParadaSpike({required this.parada, required this.onTap, super.key});

  final ParadaSenda parada;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final Color color = colorDeNodo(context, parada.estilo);
    return Semantics(
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

/// Una Ruta de ejemplo con `n` módulos, variando su estilo a propósito: el
/// primero completado, uno "actual", uno bloqueado a la mitad, para que el
/// experimento muestre los tres colores del trazo (recorrido, pendiente,
/// más allá del candado) sin depender de datos reales.
DetalleRuta _detalleDeEjemplo(int n) {
  final List<Map<String, dynamic>> modulos = <Map<String, dynamic>>[];
  for (int i = 0; i < n; i++) {
    final String estado = i == 0
        ? 'completed'
        : (i == 1 ? 'in_progress' : (i <= 2 ? 'available' : 'locked'));
    modulos.add(<String, dynamic>{
      'module_id': 'mod-$i',
      'title': 'Módulo ${i + 1}',
      'position': i + 1,
      'status': estado,
      'content_status': 'ready',
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
      'locked_reason': i > 2 ? 'Completa el módulo $i para desbloquear' : null,
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
