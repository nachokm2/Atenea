/// Fase 0b — el experimento descartable del muñeco de papel que camina.
///
/// Pregunta que responde, y solo esa: recortar y rotar seis regiones del
/// mismo dibujo estático (`base_masculino_002`) alrededor de sus pivotes
/// reales —¿se lee como caminar, o como una marioneta rota? ¿se nota el
/// corte en cadera/hombro a 120dp?
///
/// El hombro es el riesgo conocido de antemano: a diferencia de las piernas
/// (dos siluetas ya separadas por un hueco real, medido en
/// `scripts/medir_figuras.py` con la misma técnica), el brazo **no** tiene un
/// hueco de verdad respecto al torso en este dibujo — se midió con
/// `scipy.ndimage.label` y el brazo y el torso son una sola silueta conexa
/// entre el hombro y la cadera. Recortar un rectángulo para el brazo corta,
/// por fuerza, un poco de torso con él. Esa costura es exactamente lo que
/// este spike existe para enseñar, no un error a esconder.
///
/// Los números de más abajo son una medición a mano, de un único cuerpo, para
/// este spike únicamente — no el `medir_miembros.py` real de la Fase 2, que
/// mide las seis figuras y escribe una tabla, no una constante suelta.
///
/// Ver `docs/planes/mundo-caminable.md` (Fase 0) para las preguntas de
/// salida completas.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../design/arte.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';

/// Lienzo maestro sobre el que está dibujada la figura.
const double _lienzo = 1024;

const String _figura = 'base_masculino_002';

// ---------------------------------------------------------------------------
// Medidas reales de `base_masculino_002`, tomadas sobre el WebP con
// `numpy`/`scipy.ndimage.label` (silueta = alfa > 40, igual que
// `medir_figuras.py`). Nunca a mano sobre una regla en pantalla.
// ---------------------------------------------------------------------------

/// Fila donde el brazo dejaría de tocar el torso si hubiera hueco (no lo
/// hay: es donde, mirando fila a fila, el ancho pasa de "un solo tramo" a
/// "tres tramos" — torso y los dos brazos). Pivote de hombro.
const double _yHombro = 328;

/// Fila donde las dos piernas sí son dos componentes conexas distintas de
/// verdad — el hueco de la entrepierna. Pivote de cadera.
const double _yCadera = 560;

/// Fila hasta donde llega la muñeca (de ahí para abajo ya no hay brazo que
/// recortar; la mano suelta cubre el resto).
const double _yMuneca = 600;

const Rect _rectCabeza = Rect.fromLTRB(364, 40, 657, _yHombro);
const Rect _rectTorso = Rect.fromLTRB(422, _yHombro, 599, _yCadera);
const Rect _rectBrazoIzq = Rect.fromLTRB(364, _yHombro, 422, _yMuneca);
const Rect _rectBrazoDer = Rect.fromLTRB(599, _yHombro, 657, _yMuneca);
const Rect _rectPiernaIzq = Rect.fromLTRB(390, _yCadera, 505, 974);
const Rect _rectPiernaDer = Rect.fromLTRB(509, _yCadera, 625, 974);

const Offset _pivoteCabeza = Offset(510, _yHombro);
const Offset _pivoteTorso = Offset(510, _yCadera);
const Offset _pivoteHombroIzq = Offset(393, _yHombro);
const Offset _pivoteHombroDer = Offset(628, _yHombro);
const Offset _pivoteCaderaIzq = Offset(447, _yCadera);
const Offset _pivoteCaderaDer = Offset(567, _yCadera);

/// Pantalla del experimento: un muñeco de papel que camina en el sitio.
class PantallaExperimentoMarcha extends StatefulWidget {
  const PantallaExperimentoMarcha({super.key});

  @override
  State<PantallaExperimentoMarcha> createState() =>
      _PantallaExperimentoMarchaState();
}

class _PantallaExperimentoMarchaState extends State<PantallaExperimentoMarcha>
    with SingleTickerProviderStateMixin {
  late final AnimationController _control;

  double _amplitudCadera = 22; // grados
  double _amplitudBrazos = 26; // grados
  double _bob = 14; // px, en el lienzo de 1024
  double _inclinacion = 4; // grados, estática

  @override
  void initState() {
    super.initState();
    _control = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
  }

  @override
  void dispose() {
    _control.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PantallaAtenea(
      titulo: 'Spike · marcha',
      mostrarVolver: true,
      padding: EdgeInsets.zero,
      limitarAnchoLectura: false,
      cuerpo: Column(
        children: <Widget>[
          _Controles(
            amplitudCadera: _amplitudCadera,
            amplitudBrazos: _amplitudBrazos,
            bob: _bob,
            inclinacion: _inclinacion,
            alCambiar: (double cadera, double brazos, double bob, double inclinacion) =>
                setState(() {
              _amplitudCadera = cadera;
              _amplitudBrazos = brazos;
              _bob = bob;
              _inclinacion = inclinacion;
            }),
          ),
          Expanded(
            child: Center(
              child: AnimatedBuilder(
                animation: _control,
                builder: (BuildContext context, Widget? child) => _Muneco(
                  fase: _control.value * 2 * math.pi,
                  amplitudCadera: _amplitudCadera * math.pi / 180,
                  amplitudBrazos: _amplitudBrazos * math.pi / 180,
                  bob: _bob,
                  inclinacion: _inclinacion * math.pi / 180,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Controles extends StatelessWidget {
  const _Controles({
    required this.amplitudCadera,
    required this.amplitudBrazos,
    required this.bob,
    required this.inclinacion,
    required this.alCambiar,
  });

  final double amplitudCadera;
  final double amplitudBrazos;
  final double bob;
  final double inclinacion;
  final void Function(double cadera, double brazos, double bob, double inclinacion) alCambiar;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Espacio.md),
      child: Column(
        children: <Widget>[
          _Deslizador(
            etiqueta: 'Cadera',
            valor: amplitudCadera,
            max: 45,
            onChanged: (double v) => alCambiar(v, amplitudBrazos, bob, inclinacion),
          ),
          _Deslizador(
            etiqueta: 'Brazos',
            valor: amplitudBrazos,
            max: 45,
            onChanged: (double v) => alCambiar(amplitudCadera, v, bob, inclinacion),
          ),
          _Deslizador(
            etiqueta: 'Bob',
            valor: bob,
            max: 40,
            onChanged: (double v) => alCambiar(amplitudCadera, amplitudBrazos, v, inclinacion),
          ),
          _Deslizador(
            etiqueta: 'Inclinación',
            valor: inclinacion,
            max: 20,
            onChanged: (double v) => alCambiar(amplitudCadera, amplitudBrazos, bob, v),
          ),
        ],
      ),
    );
  }
}

class _Deslizador extends StatelessWidget {
  const _Deslizador({
    required this.etiqueta,
    required this.valor,
    required this.max,
    required this.onChanged,
  });

  final String etiqueta;
  final double valor;
  final double max;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        SizedBox(width: 88, child: Text(etiqueta, style: context.textos.bodySmall)),
        Expanded(
          child: Slider(
            value: valor,
            min: 0,
            max: max,
            label: valor.round().toString(),
            onChanged: onChanged,
          ),
        ),
      ],
    );
  }
}

/// El muñeco de papel: seis recortes de `cuerpoSinManos` más dos manos
/// sueltas, cada uno rotado alrededor de su pivote medido.
class _Muneco extends StatelessWidget {
  const _Muneco({
    required this.fase,
    required this.amplitudCadera,
    required this.amplitudBrazos,
    required this.bob,
    required this.inclinacion,
  });

  final double fase;
  final double amplitudCadera;
  final double amplitudBrazos;
  final double bob;
  final double inclinacion;

  @override
  Widget build(BuildContext context) {
    final double anguloPiernaIzq = amplitudCadera * math.sin(fase);
    final double anguloPiernaDer = -amplitudCadera * math.sin(fase);
    // Contralateral: cada brazo sigue la fase de la pierna del lado opuesto.
    final double anguloBrazoIzq = -amplitudBrazos * math.sin(fase);
    final double anguloBrazoDer = amplitudBrazos * math.sin(fase);
    // Dos rebotes por zancada completa (un pie apoya, luego el otro).
    final double desplazamientoBob = -bob * (1 - math.cos(2 * fase)) / 2;

    final String ruta = Arte.cuerpoSinManos(_figura);
    final String manoIzq = Arte.mano(_figura, derecha: false);
    final String manoDer = Arte.mano(_figura, derecha: true);

    return FittedBox(
      fit: BoxFit.contain,
      child: SizedBox(
        width: _lienzo,
        height: _lienzo,
        child: Transform.translate(
          offset: Offset(0, desplazamientoBob),
          child: Stack(
            children: <Widget>[
              _ParteRecortada(
                ruta: ruta,
                rect: _rectPiernaIzq,
                pivote: _pivoteCaderaIzq,
                angulo: anguloPiernaIzq,
              ),
              _ParteRecortada(
                ruta: ruta,
                rect: _rectPiernaDer,
                pivote: _pivoteCaderaDer,
                angulo: anguloPiernaDer,
              ),
              _ParteRecortada(
                ruta: ruta,
                rect: _rectTorso,
                pivote: _pivoteTorso,
                angulo: inclinacion,
              ),
              _ParteRecortada(
                ruta: ruta,
                rect: _rectBrazoIzq,
                pivote: _pivoteHombroIzq,
                angulo: anguloBrazoIzq,
              ),
              _ParteRecortada(
                ruta: ruta,
                rect: _rectBrazoDer,
                pivote: _pivoteHombroDer,
                angulo: anguloBrazoDer,
              ),
              _ManoSuelta(ruta: manoIzq, pivote: _pivoteHombroIzq, angulo: anguloBrazoIzq),
              _ManoSuelta(ruta: manoDer, pivote: _pivoteHombroDer, angulo: anguloBrazoDer),
              _ParteRecortada(
                ruta: ruta,
                rect: _rectCabeza,
                pivote: _pivoteCabeza,
                angulo: inclinacion * 0.6,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Un recorte rectangular de [ruta], rotado alrededor de [pivote] (en las
/// coordenadas del lienzo de 1024×1024 completo).
class _ParteRecortada extends StatelessWidget {
  const _ParteRecortada({
    required this.ruta,
    required this.rect,
    required this.pivote,
    required this.angulo,
  });

  final String ruta;
  final Rect rect;
  final Offset pivote;
  final double angulo;

  @override
  Widget build(BuildContext context) {
    final Alignment alineacion = Alignment(
      ((pivote.dx - rect.left) / rect.width) * 2 - 1,
      ((pivote.dy - rect.top) / rect.height) * 2 - 1,
    );
    return Positioned(
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
      child: Transform.rotate(
        angle: angulo,
        alignment: alineacion,
        child: ClipRect(
          child: Transform.translate(
            offset: Offset(-rect.left, -rect.top),
            child: SizedBox(
              width: _lienzo,
              height: _lienzo,
              child: Image.asset(ruta, fit: BoxFit.fill),
            ),
          ),
        ),
      ),
    );
  }
}

/// Una mano suelta (`Arte.mano`), ya en las coordenadas del lienzo completo
/// —no hace falta recortarla, solo rotarla con el mismo ángulo que su brazo.
class _ManoSuelta extends StatelessWidget {
  const _ManoSuelta({required this.ruta, required this.pivote, required this.angulo});

  final String ruta;
  final Offset pivote;
  final double angulo;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: 0,
      top: 0,
      width: _lienzo,
      height: _lienzo,
      child: Transform.rotate(
        angle: angulo,
        alignment: Alignment(
          (pivote.dx / _lienzo) * 2 - 1,
          (pivote.dy / _lienzo) * 2 - 1,
        ),
        child: Image.asset(ruta, fit: BoxFit.fill),
      ),
    );
  }
}
