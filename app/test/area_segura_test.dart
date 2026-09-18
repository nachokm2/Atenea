/// La barra de navegación del móvil no puede tapar los controles de la app.
///
/// En la captura que lo destapó, el botón «Entendido» de la hoja de módulo
/// bloqueado quedaba justo detrás de los tres botones de Android: se veía, pero
/// al tocarlo respondía el sistema.
///
/// La causa no era un olvido en esa hoja, sino una trampa del SDK:
/// `showModalBottomSheet(useSafeArea: true)` envuelve la hoja en
/// `SafeArea(bottom: false)` —Flutter, `material/bottom_sheet.dart:1119`—, o
/// sea que protege arriba y los lados y **deja el borde inferior descubierto a
/// propósito**. El nombre del parámetro dice lo contrario de lo que hace.
///
/// Nueve hojas se salvaban porque traían su propio `SafeArea` dentro; las ocho
/// de `hojas_aventura.dart` y `acceso.dart` no. Por eso el arreglo va en
/// `mostrarHoja`, el paso único de todas: así la próxima hoja nace protegida
/// sin que nadie tenga que acordarse.
///
/// Estas pruebas miden la posición real en pantalla fingiendo un móvil con
/// barra de navegación, que es lo único que distingue el fallo de su arreglo.
library;

import 'package:atenea/design/components.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/navegacion/armazon.dart';
import 'package:atenea/pantallas/aventura/widgets/hojas_aventura.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

/// Alto en dp de la barra de navegación que finge el dispositivo.
const double _barraDelSistema = 48;

/// Pantalla del móvil de Rodrigo, que es donde se vio el fallo.
const Size _pantalla = Size(412, 915);

const Key _llave = Key('control-de-abajo');

/// Finge un móvil con barra de navegación inferior.
///
/// Sin esto la prueba no puede fallar: el dispositivo de pruebas no tiene
/// barras del sistema, así que `SafeArea` no aparta nada y todo mide igual con
/// el arreglo y sin él.
void _conBarraDelSistema(WidgetTester tester) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = _pantalla;
  tester.view.padding = const FakeViewPadding(bottom: _barraDelSistema);
  tester.view.viewPadding = const FakeViewPadding(bottom: _barraDelSistema);
  addTearDown(tester.view.reset);
}

/// La línea que ningún control puede cruzar hacia abajo.
final double _lineaDeSeguridad = _pantalla.height - _barraDelSistema;

Future<void> _abrir(
  WidgetTester tester,
  void Function(BuildContext context) accion,
) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AteneaTheme.oscuro(),
      home: Scaffold(
        body: Builder(
          builder: (BuildContext context) => TextButton(
            onPressed: () => accion(context),
            child: const Text('abrir'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('abrir'));
  await tester.pumpAndSettle();
}

void main() {
  setUp(prepararTipografias);

  testWidgets('el contenido de una hoja termina sobre la barra del sistema',
      (WidgetTester tester) async {
    _conBarraDelSistema(tester);

    await _abrir(
      tester,
      (BuildContext context) => mostrarHoja<void>(
        context,
        constructor: (_) => const SizedBox(key: _llave, height: 120),
      ),
    );

    expect(
      tester.getBottomLeft(find.byKey(_llave)).dy,
      _lineaDeSeguridad,
      reason: 'el último control de la hoja cae bajo la barra de navegación',
    );
  });

  testWidgets('una hoja que ya se protegía no paga el hueco dos veces',
      (WidgetTester tester) async {
    // Nueve hojas traen su propio `SafeArea`. Como el de `mostrarHoja` consume
    // el hueco, el de dentro se queda a cero y el aire no se duplica. Si esto
    // fallara, esas nueve hojas habrían ganado 48 dp de vacío al arreglar las
    // otras ocho.
    _conBarraDelSistema(tester);

    await _abrir(
      tester,
      (BuildContext context) => mostrarHoja<void>(
        context,
        constructor: (_) => const SafeArea(
          child: SizedBox(key: _llave, height: 120),
        ),
      ),
    );

    expect(tester.getBottomLeft(find.byKey(_llave)).dy, _lineaDeSeguridad);
  });

  testWidgets('con el teclado abierto no se cuela un hueco muerto',
      (WidgetTester tester) async {
    // El único caso frágil del arreglo, y ocho de las hojas que toca llevan
    // `TextField`. La afirmación que hay que sostener es que `SafeArea` usa
    // `MediaQuery.padding` —que ya descuenta `viewInsets`— y no `viewPadding`.
    // Si alguien le añadiera `maintainBottomViewPadding: true`, que suena a
    // mejora y el SDK documenta como remedio para el salto al abrir el
    // teclado, cada hoja con teclado ganaría 48 dp de vacío entre su último
    // control y el teclado, y ninguna otra prueba lo vería.
    _conBarraDelSistema(tester);
    // Así es como lo entrega Android con el teclado abierto, y hay que
    // ponerlo a mano: el banco de pruebas NO deriva `padding` de
    // `viewPadding - viewInsets`, esa resta la hace el sistema en el
    // dispositivo. El teclado tapa la barra de navegación, así que el hueco
    // que hay que respetar pasa a ser cero y `viewPadding` conserva los 48 de
    // la barra que sigue ahí debajo.
    tester.view.viewInsets = const FakeViewPadding(bottom: 320);
    tester.view.padding = FakeViewPadding.zero;

    await _abrir(
      tester,
      (BuildContext context) => mostrarHoja<void>(
        context,
        constructor: (_) => const SizedBox(key: _llave, height: 120),
      ),
    );

    expect(
      tester.getBottomLeft(find.byKey(_llave)).dy,
      _pantalla.height,
      reason: 'con el teclado tapando la barra, este SafeArea no debe sumar nada',
    );
  });

  testWidgets('el «Entendido» de la hoja de módulo bloqueado es alcanzable',
      (WidgetTester tester) async {
    // La hoja exacta de la captura.
    _conBarraDelSistema(tester);

    await _abrir(
      tester,
      (BuildContext context) => explicarBloqueo(
        context,
        titulo: 'Salón de las Puertas',
        mensaje: 'El Reino todavía está escribiendo este módulo.',
        consejo: 'Te avisamos en cuanto esté listo.',
      ),
    );

    final Finder boton = find.byType(BotonPrimario);
    expect(boton, findsOneWidget);
    expect(
      tester.getBottomLeft(boton).dy,
      lessThanOrEqualTo(_lineaDeSeguridad),
      reason: 'los botones de Android tapan el «Entendido»',
    );
  });
}
