/// La geometría del sendero (`senda.dart`): pura, sin montar ningún widget.
///
/// El caso que más importa probar no es "dibuja bien" — es "no teletransporta
/// al aprendiz cuando la forja termina un módulo con la pantalla abierta".
/// Los módulos se generan de a uno (`content/rutas.py._encargar_contenido`) y
/// el total de módulos de una Ruta cambia en vivo; si el sendero repartiera
/// las paradas entre "los N módulos de hoy", la parada 2 se movería en cuanto
/// apareciera un módulo 5. Por eso la parada `i` es una función de `i` sola.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/pantallas/aventura/mundo/senda.dart';
import 'package:atenea/pantallas/aventura/widgets/nodos_mapa.dart';
import 'package:flutter_test/flutter_test.dart';

// ---------------------------------------------------------------------------
// Sobres del servidor (mismos constructores que camino_ruta_test.dart)
// ---------------------------------------------------------------------------

Map<String, dynamic> _leccion(String id, {String estado = 'not_started'}) =>
    <String, dynamic>{
      'lesson_id': id,
      'title': 'Lección $id',
      'position': 1,
      'status': estado,
      'content_status': 'ready',
      'estimated_seconds': 540,
    };

Map<String, dynamic> _desafio({bool aprobada = false}) => <String, dynamic>{
      'assessment_id': 'eval-1',
      'module_id': 'mod-1',
      'title': 'Prueba',
      'question_count': 4,
      'pass_score': 80.0,
      'max_attempts_per_day': 3,
      'content_status': 'ready',
      'attempts_used': 0,
      'best_score': null,
      'passed': aprobada,
      'can_start': true,
      'cooldown_until': null,
    };

Map<String, dynamic> _modulo(
  String id, {
  String estado = 'available',
  Map<String, dynamic>? desafio,
}) =>
    <String, dynamic>{
      'module_id': id,
      'title': 'Módulo $id',
      'position': 1,
      'status': estado,
      'content_status': 'ready',
      'lessons_total': 1,
      'lessons_completed': 0,
      'mastery': 0.0,
      'assessment': desafio,
      'topics': <Map<String, dynamic>>[
        <String, dynamic>{
          'topic_id': 'tema-$id',
          'module_id': id,
          'title': 'Tema de $id',
          'position': 1,
          'lessons': <Map<String, dynamic>>[_leccion('lec-$id')],
        },
      ],
    };

DetalleRuta _ruta(List<Map<String, dynamic>> modulos, {String estado = 'active'}) =>
    DetalleRuta.desdeJson(<String, dynamic>{
      'path': <String, dynamic>{
        'path_id': 'ruta-1',
        'title': 'El Castillo de las Consultas',
        'status': estado,
      },
      'status': estado,
      'modules': modulos,
    });

const double _ancho = 412;

void main() {
  test('N módulos dan N+1 paradas, en orden, cada una más abajo que la anterior', () {
    final Senda senda = Senda.desdeDetalle(
      _ruta(<Map<String, dynamic>>[
        _modulo('a', estado: 'completed', desafio: _desafio(aprobada: true)),
        _modulo('b', estado: 'in_progress'),
        _modulo('c', estado: 'locked'),
      ]),
      ancho: _ancho,
    );

    expect(senda.paradas, hasLength(4)); // 3 módulos + tesoro
    for (int i = 0; i < senda.paradas.length; i++) {
      expect(senda.paradas[i].indice, i);
    }
    for (int i = 0; i < senda.paradas.length - 1; i++) {
      expect(
        senda.paradas[i].centro.dy,
        lessThan(senda.paradas[i + 1].centro.dy),
        reason: 'la parada $i debe quedar arriba de la ${i + 1}',
      );
    }
  });

  test(
      'estabilidad ante crecimiento: las paradas ya visitadas no se mueven '
      'cuando la Ruta gana un módulo nuevo', () {
    final List<Map<String, dynamic>> primerosCuatro = <Map<String, dynamic>>[
      _modulo('a', estado: 'completed', desafio: _desafio(aprobada: true)),
      _modulo('b', estado: 'completed', desafio: _desafio(aprobada: true)),
      _modulo('c', estado: 'in_progress'),
      _modulo('d', estado: 'locked'),
    ];

    final Senda sendaDeCuatro =
        Senda.desdeDetalle(_ruta(primerosCuatro), ancho: _ancho);
    final Senda sendaDeSeis = Senda.desdeDetalle(
      _ruta(<Map<String, dynamic>>[
        ...primerosCuatro,
        _modulo('e', estado: 'locked'),
        _modulo('f', estado: 'locked'),
      ]),
      ancho: _ancho,
    );

    for (int i = 0; i < 4; i++) {
      expect(
        sendaDeSeis.paradas[i].centro,
        sendaDeCuatro.paradas[i].centro,
        reason: 'la parada $i no puede moverse cuando aparece un módulo nuevo',
      );
    }
  });

  test('ultimaAlcanzable se detiene justo antes del primer módulo bloqueado', () {
    final Senda senda = Senda.desdeDetalle(
      _ruta(<Map<String, dynamic>>[
        _modulo('a', estado: 'completed', desafio: _desafio(aprobada: true)),
        _modulo('b', estado: 'available'),
        _modulo('c', estado: 'locked'),
        _modulo('d', estado: 'locked'),
      ]),
      ancho: _ancho,
    );

    expect(senda.paradas[0].estilo, EstiloNodo.completado);
    // Sin ningún módulo `in_progress`, el primero `disponible` es el
    // `moduloActual` — por eso `estiloDeModulo` lo marca `actual`, no
    // `disponible`. Es la misma regla que ya usa la lista de nodos.
    expect(senda.paradas[1].estilo, EstiloNodo.actual);
    expect(senda.paradas[2].estilo, EstiloNodo.bloqueado);
    expect(senda.ultimaAlcanzable, 1);
  });

  test('el sendero pasa exactamente por cada parada', () {
    final Senda senda = Senda.desdeDetalle(
      _ruta(<Map<String, dynamic>>[
        _modulo('a', estado: 'available'),
        _modulo('b', estado: 'locked'),
      ]),
      ancho: _ancho,
    );

    for (final ParadaSenda p in senda.paradas) {
      expect(puntoEnY(yDeParada(p.indice), _ancho), p.centro);
    }
  });

  test('determinismo: misma Ruta y mismo ancho, mismo sendero', () {
    final DetalleRuta detalle = _ruta(<Map<String, dynamic>>[
      _modulo('a', estado: 'available'),
      _modulo('b', estado: 'locked'),
    ]);

    final Senda primera = Senda.desdeDetalle(detalle, ancho: _ancho);
    final Senda segunda = Senda.desdeDetalle(detalle, ancho: _ancho);

    expect(segunda.tamano, primera.tamano);
    for (int i = 0; i < primera.paradas.length; i++) {
      expect(segunda.paradas[i].centro, primera.paradas[i].centro);
      expect(segunda.paradas[i].estilo, primera.paradas[i].estilo);
    }
  });

  test('el portón está cerrado antes de un módulo bloqueado, abierto antes de uno abierto', () {
    final Senda senda = Senda.desdeDetalle(
      _ruta(<Map<String, dynamic>>[
        _modulo('a', estado: 'completed', desafio: _desafio(aprobada: true)),
        _modulo('b', estado: 'available'),
        _modulo('c', estado: 'locked'),
      ]),
      ancho: _ancho,
    );

    expect(senda.portonAntesDe(1)?.abierto, true);
    expect(senda.portonAntesDe(2)?.abierto, false);
    expect(senda.portonAntesDe(0), isNull, reason: 'la primera parada no tiene portón detrás');
  });

  test('el tesoro está bloqueado hasta que la Ruta se completa', () {
    final Senda sinCompletar = Senda.desdeDetalle(
      _ruta(
        <Map<String, dynamic>>[
          _modulo('a', estado: 'completed', desafio: _desafio(aprobada: true)),
        ],
        estado: 'active',
      ),
      ancho: _ancho,
    );
    final Senda completada = Senda.desdeDetalle(
      _ruta(
        <Map<String, dynamic>>[
          _modulo('a', estado: 'completed', desafio: _desafio(aprobada: true)),
        ],
        estado: 'completed',
      ),
      ancho: _ancho,
    );

    expect(sinCompletar.paradas.last.estilo, EstiloNodo.bloqueado);
    expect(sinCompletar.portonAntesDe(1)?.abierto, false);
    expect(completada.paradas.last.estilo, EstiloNodo.completado);
    expect(completada.portonAntesDe(1)?.abierto, true);
    expect(completada.ultimaAlcanzable, completada.paradas.last.indice);
  });

  test('una Ruta sin módulos no tiene sendero', () {
    final Senda senda = Senda.desdeDetalle(_ruta(<Map<String, dynamic>>[]), ancho: _ancho);
    expect(senda.estaVacia, isTrue);
  });
}
