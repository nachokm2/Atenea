import 'dart:io';

import 'package:atenea/navegacion/rutas.dart';
import 'package:flutter_test/flutter_test.dart';

/// El enlace del correo tiene que llegar a la pantalla **con su permiso**.
///
/// Es el único enlace de Atenea que lleva información en la consulta. Si la
/// traducción la perdiera, la pantalla se abriría vacía y quien olvidó su
/// contraseña se quedaría igual que antes, con la diferencia de haber recibido
/// un correo que no sirve para nada.
void main() {
  _esquemaDeclarado();

  test('el enlace del correo conserva el permiso', () {
    final String? destino = EnlacesProfundos.aDireccionInterna(
      'atenea://password/reset?token=abc123',
    );

    expect(destino, isNotNull);
    expect(Uri.parse(destino!).path, Rutas.nuevaContrasena);
    expect(Uri.parse(destino).queryParameters['token'], 'abc123');
  });

  test('un permiso con caracteres raros viaja entero', () {
    final String? destino = EnlacesProfundos.aDireccionInterna(
      'atenea://password/reset?token=a-b_c%2Bd',
    );

    expect(Uri.parse(destino!).queryParameters['token'], 'a-b_c+d');
  });

  test('sin permiso lleva igualmente a la pantalla, que sabe explicarlo', () {
    expect(
      EnlacesProfundos.aDireccionInterna('atenea://password/reset'),
      Rutas.nuevaContrasena,
    );
  });

  test('otra ruta bajo password no lleva a ninguna parte', () {
    expect(EnlacesProfundos.aDireccionInterna('atenea://password/otra'), isNull);
  });

  test('la pantalla se puede abrir sin sesión', () {
    // Es el caso normal: se abre justo porque no se puede entrar.
    expect(Rutas.deEntrada, contains(Rutas.nuevaContrasena));
  });
}

/// El esquema tiene que estar declarado en los dos sistemas operativos.
///
/// La traducción del enlace puede ser perfecta y no servir de nada: si el
/// sistema no sabe que `atenea://` le pertenece a esta app, el enlace del correo
/// no abre nada. Android lo declaraba desde el principio; iOS no, así que la
/// recuperación de contraseña sencillamente no existía en iPhone, y eso no se ve
/// desde ninguna pantalla ni lo nota ninguna otra prueba.
void _esquemaDeclarado() {
  group('el sistema operativo conoce atenea://', () {
    test('Android lo declara en su manifiesto', () {
      final String manifiesto =
          File('android/app/src/main/AndroidManifest.xml').readAsStringSync();

      expect(manifiesto, contains('android:scheme="atenea"'));
      expect(manifiesto, contains('android.intent.category.BROWSABLE'));
    });

    test('iOS lo declara en su Info.plist', () {
      final String plist = File('ios/Runner/Info.plist').readAsStringSync();

      expect(plist, contains('CFBundleURLTypes'));
      expect(plist, contains('CFBundleURLSchemes'));
      // El esquema, en su propia etiqueta dentro del array de esquemas.
      expect(plist, contains('<string>atenea</string>'));
    });
  });
}
