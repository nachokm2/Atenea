/// P21 — Ajustes: control sin fricción.
///
/// Cuenta, apariencia, notificaciones, objetivo diario, datos y documentos, y
/// acerca de. Cada cambio se guarda al instante contra `PUT /settings` con una
/// confirmación mínima; si el Reino no responde, el interruptor vuelve a su
/// sitio con un aviso claro.
library;

import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../data/errores.dart';
import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/sesion.dart';
import '../../navegacion/armazon.dart';
import '../../navegacion/rutas.dart';
import '../../nucleo/controlador_tema.dart';
import '../personaje/widgets/piezas.dart';

/// Versión visible de la aplicación (coincide con `pubspec.yaml`).
const String versionAtenea = '1.0.0';

/// Pantalla de Ajustes.
class PantallaAjustes extends StatefulWidget {
  const PantallaAjustes({super.key});

  @override
  State<PantallaAjustes> createState() => _PantallaAjustesState();
}

class _PantallaAjustesState extends State<PantallaAjustes> {
  /// Copia optimista mientras el servidor confirma el cambio.
  Ajustes? _borrador;
  bool _guardando = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      final ControladorSesion sesion = context.read<ControladorSesion>();
      if (sesion.ajustes == null) sesion.cargarAjustes();
    });
  }

  // -------------------------------------------------------------------------
  // Guardado
  // -------------------------------------------------------------------------

  Future<void> _aplicar(
    Ajustes optimista,
    Future<bool> Function(ControladorSesion sesion) enviar, {
    String? confirmacion,
  }) async {
    final ControladorSesion sesion = context.read<ControladorSesion>();
    setState(() {
      _borrador = optimista;
      _guardando = true;
    });
    final bool listo = await enviar(sesion);
    if (!mounted) return;
    setState(() {
      _borrador = null;
      _guardando = false;
    });
    if (!listo) {
      avisar(
        context,
        sesion.error?.mensaje ??
            'No pudimos guardar el cambio. Lo dejamos como estaba.',
        esError: true,
      );
      sesion.limpiarError();
    } else if (confirmacion != null) {
      avisar(context, confirmacion);
    }
  }

  // -------------------------------------------------------------------------
  // Acciones de cuenta
  // -------------------------------------------------------------------------

  Future<void> _cambiarContrasena() async {
    final bool? cambiada = await mostrarHoja<bool>(
      context,
      constructor: (BuildContext hoja) => const _HojaContrasena(),
    );
    if (!mounted || cambiada != true) return;
    avisar(context, 'Contraseña actualizada.');
  }

  Future<void> _cerrarSesion() async {
    final bool salir = await _confirmar(
      context,
      titulo: '¿Cierras sesión?',
      mensaje:
          'Tu progreso queda a salvo en el Reino. Puedes volver cuando '
          'quieras con tu correo.',
      textoConfirmar: 'Cerrar sesión',
    );
    if (!mounted || !salir) return;
    await context.read<ControladorSesion>().salir();
  }

  Future<void> _eliminarCuenta() async {
    final bool? confirmado = await mostrarHoja<bool>(
      context,
      constructor: (BuildContext hoja) => const _HojaEliminarCuenta(),
    );
    if (!mounted || confirmado != true) return;
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final bool listo = await sesion.eliminarCuenta();
    if (!mounted) return;
    if (!listo) {
      avisar(
        context,
        sesion.error?.mensaje ?? 'No pudimos eliminar la cuenta ahora.',
        esError: true,
      );
    }
  }

  Future<void> _elegirHora({
    required HoraLocal? actual,
    required String titulo,
    required void Function(HoraLocal hora) alElegir,
  }) async {
    final TimeOfDay? elegida = await showTimePicker(
      context: context,
      helpText: titulo,
      initialTime: TimeOfDay(
        hour: actual?.hora ?? 19,
        minute: actual?.minuto ?? 30,
      ),
    );
    if (!mounted || elegida == null) return;
    alElegir(HoraLocal(elegida.hour, elegida.minute));
  }

  // -------------------------------------------------------------------------
  // Construcción
  // -------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ControladorSesion sesion = context.watch<ControladorSesion>();
    final ControladorTema tema = context.watch<ControladorTema>();
    final Ajustes a = _borrador ?? sesion.ajustes ?? const Ajustes();
    final bool sinAjustes = sesion.ajustes == null && _borrador == null;

    return PantallaAtenea(
      titulo: 'Ajustes',
      mostrarVolver: true,
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        0,
        Espacio.md,
        Espacio.xl,
      ),
      cuerpo: ListView(
        padding: EdgeInsets.zero,
        children: <Widget>[
          if (sinAjustes)
            const Padding(
              padding: EdgeInsets.only(top: Espacio.md),
              child: EsqueletoFilas(filas: 3, alto: 96),
            ),
          _Seccion(
            titulo: 'Cuenta',
            hijos: <Widget>[
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.alternate_email_rounded),
                title: const Text('Tu correo'),
                subtitle: Text(
                  sesion.usuario?.correo ?? 'Sin correo registrado',
                ),
              ),
              _FilaAccion(
                icono: Icons.password_rounded,
                titulo: 'Cambiar contraseña',
                detalle: 'Cerrarás sesión en tus otros dispositivos',
                alTocar: _cambiarContrasena,
              ),
              _FilaAccion(
                icono: Icons.logout_rounded,
                titulo: 'Cerrar sesión',
                detalle: 'Tu progreso queda guardado',
                alTocar: _cerrarSesion,
              ),
            ],
          ),
          _Seccion(
            titulo: 'Apariencia',
            hijos: <Widget>[
              Padding(
                padding: const EdgeInsets.symmetric(vertical: Espacio.xs),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        const Icon(Icons.palette_rounded),
                        const SizedBox(width: Espacio.md),
                        Expanded(
                          child: Text(
                            'Tema del Reino',
                            style: context.textos.titleMedium,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: Espacio.xs),
                    Wrap(
                      spacing: Espacio.xs,
                      runSpacing: Espacio.xxs,
                      children: <Widget>[
                        for (final PreferenciaTema t in PreferenciaTema.values)
                          _ChipOpcion(
                            texto: t.etiqueta,
                            icono: switch (t) {
                              PreferenciaTema.sistema =>
                                Icons.brightness_auto_rounded,
                              PreferenciaTema.oscuro =>
                                Icons.nightlight_round,
                              PreferenciaTema.claro =>
                                Icons.wb_sunny_rounded,
                            },
                            activo: a.tema == t,
                            alTocar: _guardando
                                ? null
                                : () {
                                    tema.cambiar(_modoDe(t));
                                    _aplicar(
                                      a.copiarCon(tema: t),
                                      (ControladorSesion s) =>
                                          s.guardarAjustes(tema: t),
                                    );
                                  },
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              _FilaSwitch(
                icono: Icons.animation_rounded,
                titulo: 'Reducir animaciones',
                detalle: 'Las celebraciones se muestran sin movimiento',
                valor: a.reducirMovimiento,
                alCambiar: _guardando
                    ? null
                    : (bool v) => _aplicar(
                          a.copiarCon(reducirMovimiento: v),
                          (ControladorSesion s) =>
                              s.guardarAjustes(reducirMovimiento: v),
                        ),
              ),
              _FilaSwitch(
                icono: Icons.volume_up_rounded,
                titulo: 'Sonido',
                detalle: 'Aciertos, recompensas y subidas de nivel',
                valor: a.sonidoActivado,
                alCambiar: _guardando
                    ? null
                    : (bool v) => _aplicar(
                          a.copiarCon(sonidoActivado: v),
                          (ControladorSesion s) =>
                              s.guardarAjustes(sonidoActivado: v),
                        ),
              ),
              _FilaSwitch(
                icono: Icons.vibration_rounded,
                titulo: 'Vibración',
                detalle: 'Un toque suave al acertar',
                valor: a.hapticaActivada,
                alCambiar: _guardando
                    ? null
                    : (bool v) => _aplicar(
                          a.copiarCon(hapticaActivada: v),
                          (ControladorSesion s) =>
                              s.guardarAjustes(hapticaActivada: v),
                        ),
              ),
            ],
          ),
          _Seccion(
            titulo: 'Notificaciones',
            subtitulo: 'Nunca más de tres al día, y jamás en tus horas de '
                'silencio',
            hijos: <Widget>[
              _FilaSwitch(
                icono: Icons.notifications_active_rounded,
                titulo: 'Avisos en este dispositivo',
                detalle: 'Sin esto, el Reino no te escribe',
                valor: a.pushActivado,
                alCambiar: _guardando
                    ? null
                    : (bool v) => _aplicar(
                          a.copiarCon(pushActivado: v),
                          (ControladorSesion s) =>
                              s.guardarAjustes(pushActivado: v),
                        ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: Espacio.xs),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        const Icon(Icons.alarm_rounded),
                        const SizedBox(width: Espacio.md),
                        Expanded(
                          child: Text(
                            'Recordatorio diario',
                            style: context.textos.titleMedium,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: Espacio.xs),
                    Wrap(
                      spacing: Espacio.xs,
                      runSpacing: Espacio.xxs,
                      children: <Widget>[
                        for (final ModoRecordatorio m
                            in ModoRecordatorio.values)
                          _ChipOpcion(
                            texto: m.etiqueta,
                            activo: a.modoRecordatorio == m,
                            alTocar: _guardando
                                ? null
                                : () => _aplicar(
                                      a.copiarCon(modoRecordatorio: m),
                                      (ControladorSesion s) =>
                                          s.guardarAjustes(modoRecordatorio: m),
                                    ),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              if (a.modoRecordatorio == ModoRecordatorio.manual)
                _FilaAccion(
                  icono: Icons.schedule_rounded,
                  titulo: 'Hora del recordatorio',
                  detalle: a.horaRecordatorio?.texto ?? 'Sin hora fijada',
                  alTocar: () => _elegirHora(
                    actual: a.horaRecordatorio,
                    titulo: 'Hora del recordatorio',
                    alElegir: (HoraLocal h) => _aplicar(
                      a.copiarCon(horaRecordatorio: h),
                      (ControladorSesion s) =>
                          s.guardarAjustes(horaRecordatorio: h),
                      confirmacion: 'Te avisaremos a las ${h.texto}.',
                    ),
                  ),
                ),
              _FilaSwitch(
                icono: Icons.nights_stay_rounded,
                titulo: 'Segundo aviso de la noche',
                detalle: 'Solo si tu racha está en juego',
                valor: a.ultimaLlamadaActivada,
                alCambiar: _guardando
                    ? null
                    : (bool v) => _aplicar(
                          a.copiarCon(ultimaLlamadaActivada: v),
                          (ControladorSesion s) =>
                              s.guardarAjustes(ultimaLlamadaActivada: v),
                        ),
              ),
              _FilaAccion(
                icono: Icons.bedtime_rounded,
                titulo: 'Horas de silencio',
                detalle: a.silencioDesde == null || a.silencioHasta == null
                    ? 'Sin definir'
                    : 'De ${a.silencioDesde!.texto} a ${a.silencioHasta!.texto}',
                alTocar: () => _elegirHora(
                  actual: a.silencioDesde,
                  titulo: 'Silencio desde',
                  alElegir: (HoraLocal desde) async {
                    await _elegirHora(
                      actual: a.silencioHasta,
                      titulo: 'Silencio hasta',
                      alElegir: (HoraLocal hasta) => _aplicar(
                        a.copiarCon(
                          silencioDesde: desde,
                          silencioHasta: hasta,
                        ),
                        (ControladorSesion s) => s.guardarAjustes(
                          silencioDesde: desde,
                          silencioHasta: hasta,
                        ),
                        confirmacion:
                            'Silencio de ${desde.texto} a ${hasta.texto}.',
                      ),
                    );
                  },
                ),
              ),
              _FilaSwitch(
                icono: Icons.map_rounded,
                titulo: 'Tu ruta está lista',
                detalle: 'Cuando el Reino termina de construirla',
                valor: a.avisarRutaLista,
                alCambiar: _guardando
                    ? null
                    : (bool v) => _aplicar(
                          a.copiarCon(avisarRutaLista: v),
                          (ControladorSesion s) =>
                              s.guardarAjustes(avisarRutaLista: v),
                        ),
              ),
              _FilaSwitch(
                icono: Icons.local_fire_department_rounded,
                titulo: 'Racha en riesgo',
                detalle: 'Un recordatorio antes de perderla',
                valor: a.avisarRacha,
                alCambiar: _guardando
                    ? null
                    : (bool v) => _aplicar(
                          a.copiarCon(avisarRacha: v),
                          (ControladorSesion s) =>
                              s.guardarAjustes(avisarRacha: v),
                        ),
              ),
              _FilaSwitch(
                icono: Icons.flag_rounded,
                titulo: 'Misión de la mañana',
                detalle: 'Un resumen de lo que toca hoy',
                valor: a.avisarMisiones,
                alCambiar: _guardando
                    ? null
                    : (bool v) => _aplicar(
                          a.copiarCon(avisarMisiones: v),
                          (ControladorSesion s) =>
                              s.guardarAjustes(avisarMisiones: v),
                        ),
              ),
            ],
          ),
          _Seccion(
            titulo: 'Aprendizaje',
            hijos: <Widget>[
              _FilaAccion(
                icono: Icons.track_changes_rounded,
                titulo: 'Objetivo diario',
                detalle: 'Cambia la intensidad en Racha',
                alTocar: () => context.go(Rutas.racha),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: Espacio.xs),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        const Icon(Icons.translate_rounded),
                        const SizedBox(width: Espacio.md),
                        Expanded(
                          child: Text(
                            'Idioma del contenido',
                            style: context.textos.titleMedium,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: Espacio.xs),
                    Wrap(
                      spacing: Espacio.xs,
                      children: <Widget>[
                        for (final MapEntry<String, String> idioma
                            in _idiomas.entries)
                          _ChipOpcion(
                            texto: idioma.value,
                            activo: a.idiomaContenido == idioma.key,
                            alTocar: _guardando
                                ? null
                                : () => _aplicar(
                                      a.copiarCon(
                                        idiomaContenido: idioma.key,
                                      ),
                                      (ControladorSesion s) =>
                                          s.guardarAjustes(
                                        idiomaContenido: idioma.key,
                                      ),
                                      confirmacion:
                                          'El contenido nuevo se generará en '
                                          '${idioma.value.toLowerCase()}.',
                                    ),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          _Seccion(
            titulo: 'Datos y privacidad',
            hijos: <Widget>[
              _FilaAccion(
                icono: Icons.description_rounded,
                titulo: 'Mis documentos',
                detalle: 'El material que subiste para tus rutas',
                alTocar: () => mostrarHoja<void>(
                  context,
                  constructor: (BuildContext hoja) => const _HojaDocumentos(),
                ),
              ),
              _FilaAccion(
                icono: Icons.delete_forever_rounded,
                titulo: 'Eliminar mi cuenta',
                detalle: 'Se borra tu progreso y no se puede deshacer',
                peligro: true,
                alTocar: _eliminarCuenta,
              ),
            ],
          ),
          _Seccion(
            titulo: 'Acerca de',
            hijos: <Widget>[
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.shield_moon_rounded),
                title: const Text('Atenea'),
                subtitle: const Text('Versión $versionAtenea'),
              ),
              _FilaAccion(
                icono: Icons.workspace_premium_rounded,
                titulo: 'Licencias',
                detalle: 'Tipografías, iconos y librerías',
                alTocar: () => showLicensePage(
                  context: context,
                  applicationName: 'Atenea',
                  applicationVersion: versionAtenea,
                ),
              ),
            ],
          ),
          // Solo en compilaciones de depuración: la galería del sistema de
          // diseño, referencia viva de tokens y componentes.
          if (kDebugMode)
            _Seccion(
              titulo: 'Herramientas del Reino',
              subtitulo: 'Visible solo en compilaciones de desarrollo',
              hijos: <Widget>[
                _FilaAccion(
                  icono: Icons.palette_rounded,
                  titulo: 'Sistema de diseño',
                  detalle: 'Tokens, tipografía, componentes y estados',
                  alTocar: () => context.push(Rutas.galeriaEstilo),
                ),
              ],
            ),
          const SizedBox(height: Espacio.md),
          Text(
            'Tu material y tu progreso son tuyos. El oro solo compra '
            'apariencia.',
            textAlign: TextAlign.center,
            style: context.textos.bodySmall?.copyWith(
              color: context.paleta.textoSecundario,
            ),
          ),
        ],
      ),
    );
  }

  static const Map<String, String> _idiomas = <String, String>{
    'es': 'Español',
    'en': 'Inglés',
  };

  static ThemeMode _modoDe(PreferenciaTema tema) => switch (tema) {
        PreferenciaTema.sistema => ThemeMode.system,
        PreferenciaTema.oscuro => ThemeMode.dark,
        PreferenciaTema.claro => ThemeMode.light,
      };
}

// ---------------------------------------------------------------------------
// Piezas de la pantalla
// ---------------------------------------------------------------------------

class _Seccion extends StatelessWidget {
  const _Seccion({
    required this.titulo,
    required this.hijos,
    this.subtitulo,
  });

  final String titulo;
  final String? subtitulo;
  final List<Widget> hijos;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        EncabezadoSeccion(titulo: titulo, subtitulo: subtitulo),
        TarjetaAtenea(
          padding: const EdgeInsets.symmetric(
            horizontal: Espacio.md,
            vertical: Espacio.xs,
          ),
          hijo: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              for (int i = 0; i < hijos.length; i++) ...<Widget>[
                if (i > 0) const Divider(height: 1),
                hijos[i],
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _FilaSwitch extends StatelessWidget {
  const _FilaSwitch({
    required this.icono,
    required this.titulo,
    required this.detalle,
    required this.valor,
    required this.alCambiar,
  });

  final IconData icono;
  final String titulo;
  final String detalle;
  final bool valor;
  final ValueChanged<bool>? alCambiar;

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      value: valor,
      onChanged: alCambiar,
      secondary: Icon(icono),
      title: Text(titulo, style: context.textos.titleMedium),
      subtitle: Text(
        detalle,
        style: context.textos.bodySmall?.copyWith(
          color: context.paleta.textoSecundario,
        ),
      ),
    );
  }
}

class _FilaAccion extends StatelessWidget {
  const _FilaAccion({
    required this.icono,
    required this.titulo,
    required this.detalle,
    required this.alTocar,
    this.peligro = false,
  });

  final IconData icono;
  final String titulo;
  final String detalle;
  final VoidCallback alTocar;
  final bool peligro;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = peligro ? p.error : p.textoPrimario;

    return ListTile(
      contentPadding: EdgeInsets.zero,
      onTap: alTocar,
      leading: Icon(icono, color: peligro ? p.error : null),
      title: Text(
        titulo,
        style: context.textos.titleMedium?.copyWith(color: color),
      ),
      subtitle: Text(
        detalle,
        style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
      ),
      trailing: Icon(Icons.chevron_right_rounded, color: p.textoSecundario),
    );
  }
}

class _ChipOpcion extends StatelessWidget {
  const _ChipOpcion({
    required this.texto,
    required this.activo,
    required this.alTocar,
    this.icono,
  });

  final String texto;
  final bool activo;
  final VoidCallback? alTocar;
  final IconData? icono;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return ChoiceChip(
      selected: activo,
      showCheckmark: false,
      avatar: icono == null
          ? null
          : Icon(
              icono,
              size: 16,
              color: activo ? p.arcano : p.textoSecundario,
            ),
      label: Text(texto),
      labelStyle: context.textos.bodySmall?.copyWith(
        fontWeight: FontWeight.w700,
        color: activo ? p.textoPrimario : p.textoSecundario,
      ),
      selectedColor: p.arcano.withValues(alpha: 0.18),
      side: BorderSide(color: activo ? p.arcano : p.borde),
      materialTapTargetSize: MaterialTapTargetSize.padded,
      onSelected: alTocar == null ? null : (bool _) => alTocar!(),
    );
  }
}

// ---------------------------------------------------------------------------
// Cambio de contraseña
// ---------------------------------------------------------------------------

class _HojaContrasena extends StatefulWidget {
  const _HojaContrasena();

  @override
  State<_HojaContrasena> createState() => _HojaContrasenaState();
}

class _HojaContrasenaState extends State<_HojaContrasena> {
  final TextEditingController _actual = TextEditingController();
  final TextEditingController _nueva = TextEditingController();
  bool _enviando = false;
  String? _aviso;

  @override
  void dispose() {
    _actual.dispose();
    _nueva.dispose();
    super.dispose();
  }

  Future<void> _enviar() async {
    if (_nueva.text.trim().length < 8) {
      setState(() => _aviso = 'La nueva contraseña necesita 8 caracteres o más.');
      return;
    }
    setState(() {
      _enviando = true;
      _aviso = null;
    });
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final bool listo = await sesion.cambiarContrasena(
      actual: _actual.text,
      nueva: _nueva.text,
    );
    if (!mounted) return;
    setState(() => _enviando = false);
    if (listo) {
      Navigator.of(context).pop(true);
    } else {
      setState(() => _aviso = sesion.error?.mensaje ??
          'No pudimos cambiar la contraseña. Revisa la actual.');
      sesion.limpiarError();
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          Espacio.md,
          Espacio.xs,
          Espacio.md,
          MediaQuery.viewInsetsOf(context).bottom + Espacio.md,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text('Cambiar contraseña', style: context.textos.headlineSmall),
            const SizedBox(height: Espacio.xs),
            Text(
              'Al cambiarla se cierran las sesiones de tus otros dispositivos.',
              style: context.textos.bodyMedium?.copyWith(
                color: context.paleta.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.md),
            TextField(
              controller: _actual,
              obscureText: true,
              autofillHints: const <String>[AutofillHints.password],
              decoration: const InputDecoration(
                labelText: 'Contraseña actual',
              ),
            ),
            const SizedBox(height: Espacio.sm),
            TextField(
              controller: _nueva,
              obscureText: true,
              autofillHints: const <String>[AutofillHints.newPassword],
              decoration: const InputDecoration(
                labelText: 'Contraseña nueva',
                helperText: 'Al menos 8 caracteres',
              ),
            ),
            if (_aviso != null) ...<Widget>[
              const SizedBox(height: Espacio.sm),
              BandaAviso(
                icono: Icons.error_outline_rounded,
                color: context.paleta.error,
                mensaje: _aviso!,
              ),
            ],
            const SizedBox(height: Espacio.md),
            BotonPrimario(
              texto: 'Guardar contraseña',
              cargando: _enviando,
              alTocar: _enviar,
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Eliminar cuenta
// ---------------------------------------------------------------------------

class _HojaEliminarCuenta extends StatefulWidget {
  const _HojaEliminarCuenta();

  @override
  State<_HojaEliminarCuenta> createState() => _HojaEliminarCuentaState();
}

class _HojaEliminarCuentaState extends State<_HojaEliminarCuenta> {
  static const String _palabra = 'ELIMINAR';
  final TextEditingController _texto = TextEditingController();
  bool _puede = false;

  @override
  void initState() {
    super.initState();
    _texto.addListener(() {
      final bool ahora = _texto.text.trim().toUpperCase() == _palabra;
      if (ahora != _puede) setState(() => _puede = ahora);
    });
  }

  @override
  void dispose() {
    _texto.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          Espacio.md,
          Espacio.xs,
          Espacio.md,
          MediaQuery.viewInsetsOf(context).bottom + Espacio.md,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text('Eliminar tu cuenta', style: context.textos.headlineSmall),
            const SizedBox(height: Espacio.xs),
            Text(
              'Se borran tu personaje, tus rutas, tu material y todo tu '
              'progreso. No se puede deshacer.',
              style: context.textos.bodyLarge?.copyWith(
                color: p.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.md),
            TextField(
              controller: _texto,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(
                labelText: 'Escribe $_palabra para confirmar',
              ),
            ),
            const SizedBox(height: Espacio.md),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: p.error,
                foregroundColor: p.sobreArcano,
              ),
              onPressed:
                  _puede ? () => Navigator.of(context).pop(true) : null,
              child: const Text('Eliminar definitivamente'),
            ),
            const SizedBox(height: Espacio.xs),
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Conservar mi cuenta'),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Documentos subidos
// ---------------------------------------------------------------------------

class _HojaDocumentos extends StatefulWidget {
  const _HojaDocumentos();

  @override
  State<_HojaDocumentos> createState() => _HojaDocumentosState();
}

class _HojaDocumentosState extends State<_HojaDocumentos> {
  List<Documento> _documentos = const <Documento>[];
  bool _cargando = true;
  ErrorAtenea? _error;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    final Repositorios repos = context.read<Repositorios>();
    try {
      final Pagina<Documento> pagina = await repos.documentos.documentos();
      if (!mounted) return;
      setState(() {
        _documentos = pagina.elementos;
        _cargando = false;
      });
    } on ErrorAtenea catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _cargando = false;
      });
    }
  }

  Future<void> _eliminar(Documento documento) async {
    final bool confirmado = await _confirmar(
      context,
      titulo: '¿Eliminar «${documento.titulo}»?',
      mensaje:
          'Las rutas que ya se crearon con él se mantienen, pero dejará de '
          'usarse como fuente.',
      textoConfirmar: 'Eliminar',
    );
    if (!mounted || !confirmado) return;
    final Repositorios repos = context.read<Repositorios>();
    try {
      await repos.documentos.eliminar(documento.id);
      if (!mounted) return;
      avisar(context, 'Documento eliminado.');
      await _cargar();
    } on ErrorAtenea catch (e) {
      if (!mounted) return;
      avisar(context, e.mensaje, esError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.82,
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            Espacio.md,
            Espacio.xs,
            Espacio.md,
            Espacio.md,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text('Mis documentos', style: context.textos.headlineSmall),
              const SizedBox(height: Espacio.xs),
              Text(
                'El material con el que el Reino construye tus rutas.',
                style: context.textos.bodyMedium?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
              const SizedBox(height: Espacio.md),
              Flexible(child: _lista(context)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _lista(BuildContext context) {
    if (_cargando) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: Espacio.lg),
        child: EsqueletoFilas(filas: 3, alto: 64),
      );
    }
    if (_error != null) {
      return EstadoError(mensaje: _error!.mensaje, alReintentar: _cargar);
    }
    if (_documentos.isEmpty) {
      return const EstadoVacio(
        icono: Icons.folder_open_rounded,
        titulo: 'Todavía no subiste material',
        mensaje:
            'Cuando crees una Ruta con tus apuntes, aquí los verás y podrás '
            'eliminarlos.',
      );
    }
    return ListView.separated(
      shrinkWrap: true,
      itemCount: _documentos.length,
      separatorBuilder: (BuildContext context, int i) =>
          const SizedBox(height: Espacio.xs),
      itemBuilder: (BuildContext context, int i) {
        final Documento d = _documentos[i];
        final AteneaPalette p = context.paleta;
        return TarjetaAtenea(
          padding: const EdgeInsets.symmetric(
            horizontal: Espacio.sm,
            vertical: Espacio.xs,
          ),
          hijo: Row(
            children: <Widget>[
              Icon(
                d.estaListo
                    ? Icons.description_rounded
                    : Icons.hourglass_bottom_rounded,
                color: d.estaListo ? p.dominio : p.textoSecundario,
              ),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      d.titulo.isEmpty ? (d.nombreArchivo ?? 'Documento') : d.titulo,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: context.textos.titleMedium,
                    ),
                    Text(
                      <String>[
                        d.estado.etiqueta,
                        if (d.tamanoLegible.isNotEmpty) d.tamanoLegible,
                        if (d.creadoEn != null) fechaCorta(d.creadoEn!),
                      ].join(' · '),
                      style: context.textos.bodySmall?.copyWith(
                        color: p.textoSecundario,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline_rounded),
                tooltip: 'Eliminar documento',
                onPressed: () => _eliminar(d),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------
// Confirmación genérica
// ---------------------------------------------------------------------------

Future<bool> _confirmar(
  BuildContext context, {
  required String titulo,
  required String mensaje,
  required String textoConfirmar,
}) async {
  final bool? respuesta = await showDialog<bool>(
    context: context,
    builder: (BuildContext dialogo) => AlertDialog(
      title: Text(titulo),
      content: Text(mensaje),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(dialogo).pop(false),
          child: const Text('Mejor no'),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogo).pop(true),
          child: Text(textoConfirmar),
        ),
      ],
    ),
  );
  return respuesta ?? false;
}
