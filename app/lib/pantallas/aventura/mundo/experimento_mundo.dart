/// Fase 0a — el experimento descartable del sendero caminable.
///
/// Pregunta que responde, y solo esa: ¿un serpenteante vertical con 4-10
/// paradas se siente como un mundo, o como la misma lista de siempre con un
/// delay? No usa datos reales del servidor —una `Senda` de ejemplo alcanza— y
/// el caminante es un disco de color, no el avatar real: eso es la Fase 3, y
/// depende de que este experimento primero valide que vale la pena seguir.
///
/// Vive fuera del árbol de producción a propósito, enlazado solo desde la
/// galería de estilo (`kDebugMode`), para poder borrarlo entero sin dejar
/// rastro si la respuesta es "no". Ver el plan en
/// `docs/planes/mundo-caminable.md` (Fase 0) para las preguntas de salida
/// completas.
library;

import 'package:flutter/material.dart';

import '../../../datos/dtos.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import '../widgets/nodos_mapa.dart' show colorDeNodo, iconoDeNodo;
import 'pintor_senda.dart';
import 'senda.dart';

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
  // Antes del primer toque no hay adónde caminar todavía: una animación
  // inmóvil sobre sí misma para que `_Mundo` siempre tenga una `Animation`
  // válida que observar, sin un `late` que reviente en el primer build.
  late Animation<Offset> _animacion = AlwaysStoppedAnimation<Offset>(Offset.zero);

  int _cantidadDeModulos = 6;
  int _paradaActual = 0;
  String? _aviso;

  @override
  void initState() {
    super.initState();
    _control = AnimationController(vsync: this, duration: Movimiento.corta);
  }

  @override
  void dispose() {
    _control.dispose();
    super.dispose();
  }

  DetalleRuta get _detalle => _detalleDeEjemplo(_cantidadDeModulos);

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Senda senda = Senda.desdeDetalle(_detalle, ancho: 360);

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
            child: senda.estaVacia
                ? const Center(child: Text('Sin módulos de ejemplo'))
                : _Mundo(
                    senda: senda,
                    paradaActual: _paradaActual,
                    animacion: _animacion,
                    animando: _control.isAnimating,
                    alTocarParada: _tocarParada,
                  ),
          ),
        ],
      ),
    );
  }

  void _tocarParada(int indice) {
    final Senda senda = Senda.desdeDetalle(_detalle, ancho: 360);
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
      _animacion = Tween<Offset>(begin: origen, end: fin).animate(
        CurvedAnimation(parent: _control, curve: Curves.easeInOutCubic),
      );
      _paradaActual = alcanzable ? indice : _paradaActual;
    });
    _control
      ..reset()
      ..forward();
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
    required this.paradaActual,
    required this.animacion,
    required this.animando,
    required this.alTocarParada,
  });

  final Senda senda;
  final int paradaActual;
  final Animation<Offset> animacion;
  final bool animando;
  final ValueChanged<int> alTocarParada;

  @override
  State<_Mundo> createState() => _MundoState();
}

class _MundoState extends State<_Mundo> {
  final ScrollController _camara = ScrollController();

  @override
  void didUpdateWidget(covariant _Mundo oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.animando && !oldWidget.animando) {
      widget.animacion.addListener(_seguirConLaCamara);
    }
  }

  void _seguirConLaCamara() {
    if (!_camara.hasClients) return;
    final double objetivo =
        (widget.animacion.value.dy - _camara.position.viewportDimension * 0.45)
            .clamp(0, _camara.position.maxScrollExtent);
    _camara.jumpTo(objetivo);
  }

  @override
  void dispose() {
    widget.animacion.removeListener(_seguirConLaCamara);
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
            AnimatedBuilder(
              animation: widget.animacion,
              builder: (BuildContext context, Widget? child) {
                final Offset pos = widget.animando
                    ? widget.animacion.value
                    : (senda.centroDeParada(widget.paradaActual) ?? Offset.zero);
                return Positioned(
                  left: pos.dx - 16,
                  top: pos.dy - 16,
                  child: child!,
                );
              },
              child: const _Caminante(key: ValueKey<String>('caminante')),
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
                : iconoDeNodo(parada.estilo),
            color: color,
          ),
        ),
      ),
    );
  }
}

class _Caminante extends StatelessWidget {
  const _Caminante({super.key});

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Container(
      width: 32,
      height: 32,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: p.oro,
        border: Border.all(color: p.sobreOro, width: 2),
      ),
    );
  }
}

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
