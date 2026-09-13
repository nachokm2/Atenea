/// Pantalla a la que lleva el enlace del correo de recuperación.
///
/// Se abre con `atenea://password/reset?token=…`, y también con
/// `/nueva-contrasena?token=…` en la versión web. El permiso no se enseña ni se
/// pide a mano: viene en el enlace, y si falta o ya no sirve, lo que toca es
/// pedir otro desde la pantalla de acceso.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../design/tokens.dart';
import '../../estado/sesion.dart';
import '../../navegacion/rutas.dart';

/// P02b · Elegir una contraseña nueva con el permiso recibido por correo.
class PantallaNuevaContrasena extends StatefulWidget {
  const PantallaNuevaContrasena({required this.permiso, super.key});

  /// Permiso de un solo uso que venía en el enlace.
  final String? permiso;

  @override
  State<PantallaNuevaContrasena> createState() => _PantallaNuevaContrasenaState();
}

class _PantallaNuevaContrasenaState extends State<PantallaNuevaContrasena> {
  final TextEditingController _nueva = TextEditingController();
  final GlobalKey<FormState> _formulario = GlobalKey<FormState>();
  bool _oculta = true;
  bool _listo = false;

  @override
  void dispose() {
    _nueva.dispose();
    super.dispose();
  }

  String? _validar(String? valor) {
    final String v = valor ?? '';
    if (v.trim().isEmpty) return 'Escribe tu contraseña nueva.';
    if (v.length < 10) return 'Necesita al menos 10 caracteres.';
    return null;
  }

  Future<void> _guardar() async {
    final String? permiso = widget.permiso;
    if (permiso == null || permiso.isEmpty) return;
    if (!(_formulario.currentState?.validate() ?? false)) return;

    final ControladorSesion sesion = context.read<ControladorSesion>();
    final bool hecho = await sesion.restablecerContrasena(
      permiso: permiso,
      nueva: _nueva.text,
    );
    if (!mounted) return;
    if (hecho) {
      setState(() => _listo = true);
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          sesion.error?.mensaje ??
              'Ese enlace ya no sirve. Pide uno nuevo desde la pantalla de acceso.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final ControladorSesion sesion = context.watch<ControladorSesion>();
    final bool sinPermiso = (widget.permiso ?? '').isEmpty;

    return Scaffold(
      appBar: AppBar(title: const Text('Contraseña nueva')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Espacio.lg),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  if (sinPermiso)
                    ..._sinPermiso(context, paleta)
                  else if (_listo)
                    ..._hecho(context, paleta)
                  else
                    ..._formularioNueva(context, paleta, sesion),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  List<Widget> _sinPermiso(BuildContext context, AteneaPalette paleta) => <Widget>[
        Text('Falta la llave', style: context.textos.headlineSmall),
        const SizedBox(height: Espacio.sm),
        Text(
          'Este enlace no trae el permiso. Pide uno nuevo desde la pantalla de '
          'acceso: tarda un momento y no pierdes nada.',
          style: context.textos.bodyMedium?.copyWith(color: paleta.textoSecundario),
        ),
        const SizedBox(height: Espacio.lg),
        FilledButton(
          onPressed: () => context.go(Rutas.acceso),
          child: const Text('Ir a la pantalla de acceso'),
        ),
      ];

  List<Widget> _hecho(BuildContext context, AteneaPalette paleta) => <Widget>[
        Text('Llave cambiada', style: context.textos.headlineSmall),
        const SizedBox(height: Espacio.sm),
        Text(
          'Tu contraseña es la nueva y se cerraron las sesiones que había '
          'abiertas. Tu racha y tu progreso siguen donde estaban.',
          style: context.textos.bodyMedium?.copyWith(color: paleta.textoSecundario),
        ),
        const SizedBox(height: Espacio.lg),
        FilledButton(
          onPressed: () => context.go(Rutas.acceso),
          child: const Text('Entrar al Reino'),
        ),
      ];

  List<Widget> _formularioNueva(
    BuildContext context,
    AteneaPalette paleta,
    ControladorSesion sesion,
  ) =>
      <Widget>[
        Text('Elige tu llave nueva', style: context.textos.headlineSmall),
        const SizedBox(height: Espacio.sm),
        Text(
          'Al guardarla se cerrarán todas las sesiones abiertas, también las de '
          'otros dispositivos.',
          style: context.textos.bodyMedium?.copyWith(color: paleta.textoSecundario),
        ),
        const SizedBox(height: Espacio.md),
        Form(
          key: _formulario,
          child: TextFormField(
            controller: _nueva,
            obscureText: _oculta,
            enabled: !sesion.ocupado,
            autofillHints: const <String>[AutofillHints.newPassword],
            textInputAction: TextInputAction.done,
            decoration: InputDecoration(
              labelText: 'Contraseña nueva',
              suffixIcon: IconButton(
                onPressed: () => setState(() => _oculta = !_oculta),
                icon: Icon(_oculta ? Icons.visibility_rounded : Icons.visibility_off_rounded),
                tooltip: _oculta ? 'Mostrar contraseña' : 'Ocultar contraseña',
              ),
            ),
            validator: _validar,
            onFieldSubmitted: (_) => _guardar(),
          ),
        ),
        const SizedBox(height: Espacio.lg),
        FilledButton(
          onPressed: sesion.ocupado ? null : _guardar,
          child: sesion.ocupado
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Guardar y entrar'),
        ),
      ];
}
