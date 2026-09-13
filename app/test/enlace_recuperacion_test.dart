import 'package:atenea/navegacion/rutas.dart';
import 'package:flutter_test/flutter_test.dart';

/// El enlace del correo tiene que llegar a la pantalla **con su permiso**.
///
/// Es el único enlace de Atenea que lleva información en la consulta. Si la
/// traducción la perdiera, la pantalla se abriría vacía y quien olvidó su
/// contraseña se quedaría igual que antes, con la diferencia de haber recibido
/// un correo que no sirve para nada.
void main() {
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
