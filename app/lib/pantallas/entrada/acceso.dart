/// P02 — Registro e inicio de sesión.
///
/// Una sola pantalla con dos modos (crear cuenta / entrar) para no duplicar
/// pasos. No se pide el nombre: el héroe se bautiza en P03, como fija la ficha
/// del documento de UX.
///
/// Estados cubiertos: carga (el botón gira y el formulario queda inerte),
/// credenciales incorrectas, correo ya registrado (ofrece entrar con un
/// toque), validación del servidor por campo y falta de conexión con
/// reintento. Al acertar, el enrutador se encarga del destino: P03 si la
/// cuenta es nueva, Inicio si ya hay héroe.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../data/errores.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/sesion.dart';
import '../../navegacion/armazon.dart';
import 'widgets/piezas.dart';

/// Acceso al Reino: crear cuenta o entrar.
class PantallaAcceso extends StatefulWidget {
  const PantallaAcceso({super.key});

  @override
  State<PantallaAcceso> createState() => _PantallaAccesoState();
}

class _PantallaAccesoState extends State<PantallaAcceso> {
  final GlobalKey<FormState> _formulario = GlobalKey<FormState>();
  final TextEditingController _correo = TextEditingController();
  final TextEditingController _contrasena = TextEditingController();
  final FocusNode _focoContrasena = FocusNode();

  bool _registrando = true;
  bool _oculta = true;
  bool _acepta = false;
  bool _faltaAceptar = false;
  bool _leidoModo = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_leidoModo) return;
    _leidoModo = true;
    // P01 entra con `?modo=entrar` cuando el usuario dice "Ya tengo cuenta".
    final String? modo =
        GoRouterState.of(context).uri.queryParameters['modo'];
    if (modo == 'entrar') _registrando = false;
  }

  @override
  void dispose() {
    _correo.dispose();
    _contrasena.dispose();
    _focoContrasena.dispose();
    super.dispose();
  }

  void _cambiarModo(bool registrando) {
    if (_registrando == registrando) return;
    setState(() {
      _registrando = registrando;
      _faltaAceptar = false;
    });
    context.read<ControladorSesion>().limpiarError();
  }

  Future<void> _enviar() async {
    final ControladorSesion sesion = context.read<ControladorSesion>();
    if (sesion.ocupado) return;
    FocusScope.of(context).unfocus();
    sesion.limpiarError();

    final bool valido = _formulario.currentState?.validate() ?? false;
    if (_registrando && !_acepta) {
      setState(() => _faltaAceptar = true);
    }
    if (!valido || (_registrando && !_acepta)) {
      HapticFeedback.lightImpact();
      return;
    }

    final String correo = _correo.text.trim();
    final String clave = _contrasena.text;
    if (_registrando) {
      await sesion.registrar(correo: correo, contrasena: clave);
    } else {
      await sesion.entrar(correo: correo, contrasena: clave);
    }
    // El enrutador redirige solo: P03 si la cuenta es nueva, Inicio si no.
  }

  String? _validarContrasena(String? valor) {
    final String v = valor ?? '';
    if (v.isEmpty) return 'Escribe tu contraseña.';
    if (_registrando && v.length < 8) {
      return 'Usa al menos 8 caracteres.';
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final ControladorSesion sesion = context.watch<ControladorSesion>();
    final ErrorAtenea? error = sesion.error;

    return Scaffold(
      backgroundColor: paleta.fondo,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: Medida.lecturaMax),
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(
                Espacio.md,
                Espacio.lg,
                Espacio.md,
                Espacio.xl,
              ),
              child: Form(
                key: _formulario,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    // --- Cabecera --------------------------------------
                    const Center(child: EmblemaAtenea(tamano: 76)),
                    const SizedBox(height: Espacio.md),
                    Text(
                      _registrando ? 'Crea tu cuenta' : 'Entra al Reino',
                      textAlign: TextAlign.center,
                      style: context.textos.displaySmall,
                    ),
                    const SizedBox(height: Espacio.xs),
                    Text(
                      _registrando
                          ? 'Un minuto y ya estarás dentro. Tu héroe se crea en el paso siguiente.'
                          : 'Tu racha, tu oro y tu ruta te están esperando.',
                      textAlign: TextAlign.center,
                      style: context.textos.bodyLarge?.copyWith(
                        color: paleta.textoSecundario,
                      ),
                    ),
                    const SizedBox(height: Espacio.lg),

                    // --- Modo -------------------------------------------
                    SelectorPestanas(
                      etiquetas: const <String>['Crear cuenta', 'Entrar'],
                      iconos: const <IconData>[
                        Icons.person_add_alt_1_rounded,
                        Icons.login_rounded,
                      ],
                      indice: _registrando ? 0 : 1,
                      alCambiar: (int i) => _cambiarModo(i == 0),
                    ),
                    const SizedBox(height: Espacio.lg),

                    // --- Campos ------------------------------------------
                    TextFormField(
                      controller: _correo,
                      enabled: !sesion.ocupado,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      autocorrect: false,
                      autofillHints: const <String>[AutofillHints.email],
                      validator: _validarCorreo,
                      onFieldSubmitted: (_) => _focoContrasena.requestFocus(),
                      decoration: const InputDecoration(
                        labelText: 'Correo',
                        hintText: 'tu@correo.com',
                        prefixIcon: Icon(Icons.alternate_email_rounded),
                      ),
                    ),
                    const SizedBox(height: Espacio.sm),
                    TextFormField(
                      controller: _contrasena,
                      focusNode: _focoContrasena,
                      enabled: !sesion.ocupado,
                      obscureText: _oculta,
                      textInputAction: TextInputAction.done,
                      autofillHints: <String>[
                        _registrando
                            ? AutofillHints.newPassword
                            : AutofillHints.password,
                      ],
                      validator: _validarContrasena,
                      onFieldSubmitted: (_) => _enviar(),
                      decoration: InputDecoration(
                        labelText: 'Contraseña',
                        helperText: _registrando ? 'Al menos 8 caracteres.' : null,
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        suffixIcon: IconButton(
                          tooltip: _oculta
                              ? 'Mostrar contraseña'
                              : 'Ocultar contraseña',
                          icon: Icon(
                            _oculta
                                ? Icons.visibility_rounded
                                : Icons.visibility_off_rounded,
                          ),
                          onPressed: () => setState(() => _oculta = !_oculta),
                        ),
                      ),
                    ),

                    // --- Términos ----------------------------------------
                    if (_registrando) ...<Widget>[
                      const SizedBox(height: Espacio.xs),
                      _Terminos(
                        aceptado: _acepta,
                        falta: _faltaAceptar,
                        habilitado: !sesion.ocupado,
                        alCambiar: (bool v) => setState(() {
                          _acepta = v;
                          if (v) _faltaAceptar = false;
                        }),
                        alLeer: () => _mostrarTerminos(context),
                      ),
                    ],

                    // --- Error del Reino ----------------------------------
                    if (error != null) ...<Widget>[
                      const SizedBox(height: Espacio.md),
                      _avisoDeError(context, sesion, error),
                    ],

                    const SizedBox(height: Espacio.lg),
                    BotonPrimario(
                      texto: _registrando ? 'Crear cuenta' : 'Entrar',
                      icono: _registrando
                          ? Icons.auto_awesome_rounded
                          : Icons.shield_moon_rounded,
                      cargando: sesion.ocupado,
                      alTocar: _enviar,
                    ),

                    const SizedBox(height: Espacio.xs),
                    if (_registrando)
                      TextButton(
                        onPressed: sesion.ocupado
                            ? null
                            : () => _cambiarModo(false),
                        child: const Text('¿Ya tienes cuenta? Entra aquí'),
                      )
                    else ...<Widget>[
                      TextButton(
                        onPressed:
                            sesion.ocupado ? null : () => _cambiarModo(true),
                        child: const Text('¿Aún no tienes cuenta? Créala'),
                      ),
                      TextButton(
                        onPressed: sesion.ocupado
                            ? null
                            : () => _mostrarRecuperacion(context),
                        child: const Text('Olvidé mi contraseña'),
                      ),
                    ],

                    const SizedBox(height: Espacio.md),
                    Text(
                      'Nunca pedimos dinero para avanzar: el Oro del Reino solo '
                      'se gana aprendiendo.',
                      textAlign: TextAlign.center,
                      style: context.textos.bodySmall?.copyWith(
                        color: paleta.textoSecundario,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// Traduce el error a una salida concreta, no a un callejón.
  Widget _avisoDeError(
    BuildContext context,
    ControladorSesion sesion,
    ErrorAtenea error,
  ) {
    final String codigo = error.codigo.toUpperCase();
    final AteneaPalette paleta = context.paleta;

    if (codigo == 'EMAIL_ALREADY_EXISTS') {
      return AvisoEnLinea(
        icono: Icons.info_outline_rounded,
        color: paleta.info,
        mensaje: 'Ese correo ya tiene cuenta en el Reino.',
        textoAccion: 'Entrar con este correo',
        alTocarAccion: () => _cambiarModo(false),
      );
    }

    if (codigo == 'INVALID_CREDENTIALS') {
      return const AvisoEnLinea(
        mensaje: 'Correo o contraseña incorrectos. Revisa e inténtalo otra vez.',
      );
    }

    if (codigo == 'VALIDATION_ERROR') {
      return AvisoEnLinea(mensaje: _mensajeDeCampos(error));
    }

    return AvisoEnLinea(
      mensaje: error.mensaje,
      icono: error.codigo == 'sin_conexion'
          ? Icons.wifi_off_rounded
          : Icons.error_outline_rounded,
      textoAccion: error.esReintentable ? 'Reintentar' : null,
      alTocarAccion: error.esReintentable ? _enviar : null,
    );
  }

  String _mensajeDeCampos(ErrorAtenea error) {
    final Object? campos = error.detalles?['field_errors'];
    if (campos is List && campos.isNotEmpty) {
      final Iterable<String> mensajes = campos
          .whereType<Map<dynamic, dynamic>>()
          .map((Map<dynamic, dynamic> m) => '${m['message'] ?? ''}')
          .where((String m) => m.isNotEmpty);
      if (mensajes.isNotEmpty) return mensajes.join(' ');
    }
    return error.mensaje;
  }

  Future<void> _mostrarTerminos(BuildContext context) {
    return mostrarHoja<void>(
      context,
      constructor: (BuildContext hoja) => const _HojaTexto(
        titulo: 'Términos y privacidad',
        parrafos: <String>[
          'Atenea guarda tu correo para identificarte, y tu progreso de '
              'aprendizaje (XP, Oro, racha, dominio y respuestas) para poder '
              'construir tu ruta y mostrarte cuánto avanzas.',
          'El material que subas se usa únicamente para generar tus lecciones '
              'y para citarte la fuente de cada explicación. Puedes borrar un '
              'documento cuando quieras desde tu ruta.',
          'No vendemos tus datos ni mostramos publicidad. El Oro del Reino no '
              'se compra con dinero real: solo se gana aprendiendo.',
          'Puedes eliminar tu cuenta y todo tu progreso desde Perfil › '
              'Ajustes.',
        ],
      ),
    );
  }

  Future<void> _mostrarRecuperacion(BuildContext context) {
    return mostrarHoja<void>(
      context,
      constructor: (BuildContext hoja) =>
          _HojaRecuperacion(correoInicial: _correo.text.trim()),
    );
  }
}

/// Pide el enlace para elegir una contraseña nueva.
///
/// Siempre dice lo mismo al terminar, haya cuenta o no con ese correo. No es
/// vaguedad: responder distinto convertiría esta hoja en una forma cómoda de
/// averiguar quién tiene cuenta en Atenea, probando direcciones de una en una.
class _HojaRecuperacion extends StatefulWidget {
  const _HojaRecuperacion({required this.correoInicial});

  /// Lo que ya había escrito en el formulario de acceso, para no repetirlo.
  final String correoInicial;

  @override
  State<_HojaRecuperacion> createState() => _HojaRecuperacionState();
}

class _HojaRecuperacionState extends State<_HojaRecuperacion> {
  late final TextEditingController _correo =
      TextEditingController(text: widget.correoInicial);
  final GlobalKey<FormState> _formulario = GlobalKey<FormState>();
  bool _enviado = false;

  @override
  void dispose() {
    _correo.dispose();
    super.dispose();
  }

  Future<void> _enviar() async {
    if (!(_formulario.currentState?.validate() ?? false)) return;
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final bool salio = await sesion.pedirRecuperacion(_correo.text.trim());
    if (!mounted) return;
    if (salio) {
      setState(() => _enviado = true);
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          sesion.error?.mensaje ?? 'No pudimos enviarlo. Inténtalo otra vez.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final ControladorSesion sesion = context.watch<ControladorSesion>();

    return Padding(
      padding: const EdgeInsets.fromLTRB(Espacio.lg, 0, Espacio.lg, Espacio.xl),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text('¿Perdiste la llave?', style: context.textos.headlineSmall),
          const SizedBox(height: Espacio.sm),
          if (_enviado) ...<Widget>[
            Text(
              'Si esa dirección tiene cuenta en el Reino, el enlace ya va en '
              'camino. Revisa tu correo, y también la carpeta de no deseados.',
              style: context.textos.bodyMedium?.copyWith(
                color: paleta.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.xs),
            Text(
              'Caduca en media hora y solo sirve una vez.',
              style: context.textos.bodySmall?.copyWith(
                color: paleta.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.lg),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Entendido'),
            ),
          ] else ...<Widget>[
            Text(
              'Escribe el correo de tu cuenta y te enviamos un enlace para '
              'elegir una contraseña nueva. No pierdes ni tu racha ni tu '
              'progreso.',
              style: context.textos.bodyMedium?.copyWith(
                color: paleta.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.md),
            Form(
              key: _formulario,
              child: TextFormField(
                controller: _correo,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                enabled: !sesion.ocupado,
                textInputAction: TextInputAction.done,
                decoration: const InputDecoration(
                  labelText: 'Correo',
                  hintText: 'tu@correo.cl',
                ),
                validator: _validarCorreo,
                onFieldSubmitted: (_) => _enviar(),
              ),
            ),
            const SizedBox(height: Espacio.lg),
            FilledButton(
              onPressed: sesion.ocupado ? null : _enviar,
              child: sesion.ocupado
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Enviarme el enlace'),
            ),
          ],
        ],
      ),
    );
  }
}

/// Casilla única de aceptación, con el detalle a un toque.
class _Terminos extends StatelessWidget {
  const _Terminos({
    required this.aceptado,
    required this.falta,
    required this.habilitado,
    required this.alCambiar,
    required this.alLeer,
  });

  final bool aceptado;
  final bool falta;
  final bool habilitado;
  final ValueChanged<bool> alCambiar;
  final VoidCallback alLeer;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: <Widget>[
            SizedBox(
              width: Medida.areaTactilMin,
              height: Medida.areaTactilMin,
              child: Checkbox(
                value: aceptado,
                onChanged: habilitado
                    ? (bool? v) => alCambiar(v ?? false)
                    : null,
                semanticLabel: 'Acepto los términos y la privacidad',
              ),
            ),
            Expanded(
              child: GestureDetector(
                onTap: habilitado ? () => alCambiar(!aceptado) : null,
                child: Text(
                  'Acepto los términos y la política de privacidad.',
                  style: context.textos.bodyMedium?.copyWith(
                    color: paleta.textoSecundario,
                  ),
                ),
              ),
            ),
            TextButton(
              onPressed: alLeer,
              child: const Text('Leer'),
            ),
          ],
        ),
        if (falta)
          Padding(
            padding: const EdgeInsets.only(left: Espacio.sm),
            child: Text(
              'Necesitamos tu visto bueno para abrirte las puertas.',
              style: context.textos.bodySmall?.copyWith(color: paleta.error),
            ),
          ),
      ],
    );
  }
}

/// Valida un correo escrito a mano, en la pantalla y en la hoja.
String? _validarCorreo(String? valor) {
  final String v = (valor ?? '').trim();
  if (v.isEmpty) return 'Escribe tu correo.';
  final bool formaValida = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$').hasMatch(v);
  if (!formaValida) return 'Ese correo no parece completo.';
  return null;
}

/// Hoja de texto corrido reutilizada por términos y recuperación.
class _HojaTexto extends StatelessWidget {
  const _HojaTexto({required this.titulo, required this.parrafos});

  final String titulo;
  final List<String> parrafos;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        Espacio.lg,
        0,
        Espacio.lg,
        Espacio.xl,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(titulo, style: context.textos.headlineSmall),
          const SizedBox(height: Espacio.sm),
          for (final String p in parrafos) ...<Widget>[
            Text(
              p,
              style: context.textos.bodyLarge?.copyWith(
                color: paleta.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.sm),
          ],
          const SizedBox(height: Espacio.xs),
          FilledButton(
            onPressed: () => Navigator.of(context).maybePop(),
            child: const Text('Entendido'),
          ),
        ],
      ),
    );
  }
}
