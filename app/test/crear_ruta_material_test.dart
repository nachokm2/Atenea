/// P05 se pinta entera, y los dos botones de material se ven.
///
/// Rodrigo mandó una captura en la que, entre «Opcional, pero cambia todo…» y
/// «PDF, DOCX, TXT y MD…», había un hueco vacío del alto exacto de una fila de
/// botones. Ahí van «Agregar archivos» y «Pegar texto», que son la única forma
/// de aportar documentos a una ruta.
///
/// La causa no era un `if` ni un color: era una **excepción de maquetación**.
/// El tema da a los botones `minimumSize: Size.fromHeight(48)`, y en Flutter
/// eso **no** significa «alto mínimo 48»:
/// `const Size.fromHeight(double height) : super(double.infinity, height)`
/// —ancho mínimo **infinito**—. Es el truco con el que los botones salen a
/// ancho completo, y funciona mientras alguien acote el ancho. El primero iba
/// en un `Expanded` y sobrevivía; el segundo llegaba sin acotar y la fila
/// entera moría con «BoxConstraints forces an infinite width».
///
/// Y ahí está lo que lo hizo invisible: en depuración eso pinta una franja
/// roja, pero **en release el subárbol simplemente no se pinta**. No hay error,
/// no hay aviso, no hay franja: hay un hueco. Por eso lo encontró una captura
/// del móvil y no lo encontraron ciento noventa y dos pruebas verdes.
library;

import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/estado/aventura.dart';
import 'package:atenea/pantallas/aventura/crear_ruta.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'ayudas.dart';

/// Monta la pantalla real, no una réplica.
///
/// Una copia del `Row` dentro del fichero de pruebas seguiría verde el día que
/// alguien tocara la pantalla, que es justo lo que hay que impedir.
/// `PantallaCrearRuta` no pide red al construirse: su `initState` solo lee el
/// objetivo del controlador.
Future<void> _montar(WidgetTester tester, Size tamano) async {
  await tester.binding.setSurfaceSize(tamano);
  addTearDown(() => tester.binding.setSurfaceSize(null));

  final Repositorios repos = repositoriosDePrueba(AlmacenTokensFalso());
  await tester.pumpWidget(
    MaterialApp(
      theme: AteneaTheme.oscuro(),
      home: ChangeNotifierProvider<ControladorAventura>(
        create: (_) => ControladorAventura(repos),
        child: const PantallaCrearRuta(),
      ),
    ),
  );
  await tester.pump();

  // La sección de material es el tercer paso y queda bajo el pliegue en un
  // móvil: el `ListView` no construye lo que no se ve, así que hay que llegar
  // hasta ella como llega el aprendiz.
  await tester.dragUntilVisible(
    find.text('Tu material'),
    find.byType(Scrollable).first,
    const Offset(0, -220),
  );
  await tester.pump();
}

void main() {
  setUp(prepararTipografias);

  for (final Size tamano in <Size>[
    const Size(320, 640),
    const Size(412, 915),
    const Size(800, 1280),
  ]) {
    final String medida = '${tamano.width.toInt()}×${tamano.height.toInt()}';
    testWidgets('los dos botones de material se pintan · $medida',
        (WidgetTester tester) async {
      await _montar(tester, tamano);

      // Lo primero, y lo que de verdad falló: ninguna excepción de maquetación.
      // Sin esta comprobación, las búsquedas de abajo podrían encontrar los
      // widgets en el árbol y el aprendiz seguir sin ver nada, porque lo que
      // reventaba era la fase de medida, no la de construcción.
      expect(
        tester.takeException(),
        isNull,
        reason: 'la pantalla lanza al maquetar: en release eso es un hueco vacío',
      );

      expect(find.text('Agregar archivos'), findsOneWidget);
      expect(find.text('Pegar texto'), findsOneWidget);

      for (final String etiqueta in <String>['Agregar archivos', 'Pegar texto']) {
        final Size caja = tester.getSize(find.text(etiqueta));
        expect(caja.width, greaterThan(0), reason: '«$etiqueta» sin ancho');
        expect(caja.height, greaterThan(0), reason: '«$etiqueta» sin alto');
      }
    });
  }

  testWidgets('la promesa del material aparece junto a los botones',
      (WidgetTester tester) async {
    // Si la fila desaparece, esto sigue verde: el texto está fuera de ella.
    // Va aquí para dejar claro qué parte de la sección cubre cada aserción.
    await _montar(tester, const Size(412, 915));

    expect(find.text('Tu material'), findsOneWidget);
    expect(find.textContaining('PDF, DOCX, TXT y MD'), findsOneWidget);
  });
}
