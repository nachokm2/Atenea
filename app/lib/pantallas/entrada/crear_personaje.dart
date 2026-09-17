/// P03 — Creación de personaje.
///
/// La pieza central del día 1: en menos de noventa segundos el usuario tiene
/// un héroe con el que identificarse, sin bloquearse en decisiones. Todo
/// arranca con un valor por defecto, así que se puede confirmar sin tocar
/// nada, y el botón "Aleatorio" resuelve la duda en un toque.
///
/// Reglas que se cumplen aquí:
///
/// - **Elección libre**: ninguna opción está condicionada por el género. La
///   Orden solo cambia el atuendo y el título narrativo (§5 del brief), y se
///   dice explícitamente en pantalla.
/// - **Vista previa en vivo**: el muñeco por capas se repinta al instante con
///   las mismas claves que viajan a la API.
/// - **El servidor manda**: la app no calcula XP, Oro ni nivel. Al crear el
///   personaje llega un `RewardsReceipt` con la bolsa de bienvenida y el kit
///   inicial, y se entrega tal cual a la [ColaCelebraciones].
/// - **Nunca se pierde la selección**: si el guardado falla, el error se
///   muestra con reintento y todos los rasgos siguen ahí.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/errores.dart';
import '../../datos/repositorios.dart';
import '../../design/arte.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../personaje/widgets/avatar_capas.dart';
import '../../estado/celebraciones.dart';
import '../../estado/sesion.dart';
import 'widgets/avatar_lienzo.dart';
import 'widgets/catalogo_avatar.dart';
import 'widgets/piezas.dart';

/// Longitud del nombre aceptada por la API (`characters.name`).
const int _minNombre = 3;
const int _maxNombre = 20;

// ---------------------------------------------------------------------------
// Estado del borrador
// ---------------------------------------------------------------------------

/// Borrador del héroe mientras se elige; vive solo durante P03.
class ControladorCreacionPersonaje extends ChangeNotifier {
  ControladorCreacionPersonaje({
    required Repositorios repositorios,
    String nombreSugerido = '',
  })  : _repos = repositorios,
        _nombre = nombreSugerido;

  final Repositorios _repos;
  final math.Random _azar = math.Random();

  String _nombre;
  Arquetipo _orden = Arquetipo.acero;
  RasgosAvatar _rasgos = const RasgosAvatar();
  bool _guardando = false;
  ErrorAtenea? _error;
  String? _errorNombreServidor;

  /// Clave de idempotencia de la creación: se conserva mientras el cuerpo no
  /// cambie, para que un reintento no otorgue dos bolsas de bienvenida.
  String? _clave;

  /// Nombre escrito, sin recortar.
  String get nombre => _nombre;

  /// Orden elegida.
  Arquetipo get orden => _orden;

  /// Rasgos elegidos, listos para viajar a la API.
  RasgosAvatar get rasgos => _rasgos;

  /// ¿Hay una creación en curso?
  bool get guardando => _guardando;

  /// Último fallo del Reino, ya en español.
  ErrorAtenea? get error => _error;

  /// Mensaje del servidor sobre el campo `name`, si lo hubo.
  String? get errorNombreServidor => _errorNombreServidor;

  /// Identidad visual de la Orden elegida.
  OrdenVisual get visual => CatalogoAvatar.orden(_orden);

  /// Validación local del nombre (3–20 caracteres).
  String? get mensajeNombre {
    final String v = _nombre.trim();
    if (v.isEmpty) return 'Tu héroe necesita un nombre.';
    if (v.characters.length < _minNombre) {
      return 'Al menos $_minNombre caracteres.';
    }
    if (v.characters.length > _maxNombre) {
      return 'Como máximo $_maxNombre caracteres.';
    }
    return null;
  }

  /// ¿Se puede confirmar ya?
  bool get puedeConfirmar => mensajeNombre == null && !_guardando;

  void fijarNombre(String valor) {
    if (_nombre == valor) return;
    _nombre = valor;
    _errorNombreServidor = null;
    _invalidarClave();
    notifyListeners();
  }

  void fijarOrden(Arquetipo valor) {
    if (!CatalogoAvatar.orden(valor).disponible || _orden == valor) return;
    _orden = valor;
    _invalidarClave();
    notifyListeners();
  }

  void fijarRasgos({
    TipoCuerpo? tipoCuerpo,
    String? tonoPiel,
    String? rostro,
    String? orejas,
    String? cabello,
    String? colorCabello,
    FormaTrato? formaTrato,
  }) {
    _rasgos = _rasgos.copiarCon(
      tipoCuerpo: tipoCuerpo,
      tonoPiel: tonoPiel,
      rostro: rostro,
      orejas: orejas,
      cabello: cabello,
      colorCabello: colorCabello,
      formaTrato: formaTrato,
    );
    _invalidarClave();
    notifyListeners();
  }

  /// Rasgos y Orden al azar; el nombre y la forma de tratamiento no se tocan.
  void aleatorio() {
    _rasgos = CatalogoAvatar.rasgosAlAzar(_azar, _rasgos);
    final List<Arquetipo> ordenes = CatalogoAvatar.ordenesDisponibles;
    _orden = ordenes[_azar.nextInt(ordenes.length)];
    _invalidarClave();
    notifyListeners();
  }

  /// Crea el personaje en el Reino. Devuelve `null` si algo falló; en ese caso
  /// [error] explica qué pasó y la selección queda intacta.
  Future<Personaje?> crear() async {
    if (_guardando) return null;
    _guardando = true;
    _error = null;
    _errorNombreServidor = null;
    notifyListeners();
    try {
      _clave ??= claveIdempotencia();
      final Personaje creado = await _repos.personaje.crear(
        nombre: _nombre.trim(),
        arquetipo: _orden,
        tipoCuerpo: _rasgos.tipoCuerpo,
        tonoPiel: _rasgos.tonoPiel,
        rostro: _rasgos.rostro,
        orejas: _rasgos.orejas,
        cabello: _rasgos.cabello,
        colorCabello: _rasgos.colorCabello,
        formaTrato: _rasgos.formaTrato,
        clave: _clave,
      );
      return creado;
    } catch (e) {
      final ErrorAtenea traducido = e is ErrorAtenea
          ? e
          : const ErrorAtenea(
              codigo: 'inesperado',
              mensaje: 'Ocurrió algo inesperado al forjar tu héroe.',
            );
      _error = traducido;
      _errorNombreServidor = _mensajeDelCampo(traducido, 'name');
      // Un rechazo por validación significa que el cuerpo no sirve: la clave
      // deja de ser reutilizable.
      if (traducido.estadoHttp == 422) _invalidarClave();
      return null;
    } finally {
      _guardando = false;
      notifyListeners();
    }
  }

  void limpiarError() {
    if (_error == null) return;
    _error = null;
    notifyListeners();
  }

  void _invalidarClave() => _clave = null;

  static String? _mensajeDelCampo(ErrorAtenea error, String campo) {
    final Object? campos = error.detalles?['field_errors'];
    if (campos is! List) return null;
    for (final Object? entrada in campos) {
      if (entrada is Map && '${entrada['field']}' == campo) {
        final String mensaje = '${entrada['message'] ?? ''}';
        if (mensaje.isNotEmpty) return mensaje;
      }
    }
    return null;
  }
}

// ---------------------------------------------------------------------------
// Pantalla
// ---------------------------------------------------------------------------

/// Creación del héroe: Orden, cuerpo, rostro, cabello y nombre.
class PantallaCrearPersonaje extends StatelessWidget {
  const PantallaCrearPersonaje({super.key});

  @override
  Widget build(BuildContext context) {
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final Repositorios repos = context.read<Repositorios>();

    return ChangeNotifierProvider<ControladorCreacionPersonaje>(
      create: (_) => ControladorCreacionPersonaje(
        repositorios: repos,
        nombreSugerido: _sugerirNombre(sesion.usuario?.correo),
      ),
      child: const _CuerpoCrearPersonaje(),
    );
  }

  /// Propone el nombre a partir del correo, para no dejar el campo vacío.
  static String _sugerirNombre(String? correo) {
    final String c = (correo ?? '').trim();
    if (c.isEmpty) return '';
    final int arroba = c.indexOf('@');
    String base = arroba > 0 ? c.substring(0, arroba) : c;
    base = base.replaceAll(RegExp(r'[^a-zA-ZáéíóúñÁÉÍÓÚÑ ]'), ' ').trim();
    if (base.length < _minNombre) return '';
    if (base.characters.length > _maxNombre) {
      base = base.characters.take(_maxNombre).toString();
    }
    return base[0].toUpperCase() + base.substring(1);
  }
}

class _CuerpoCrearPersonaje extends StatefulWidget {
  const _CuerpoCrearPersonaje();

  @override
  State<_CuerpoCrearPersonaje> createState() => _CuerpoCrearPersonajeState();
}

class _CuerpoCrearPersonajeState extends State<_CuerpoCrearPersonaje> {
  late final TextEditingController _nombre;
  int _pestana = 0;

  @override
  void initState() {
    super.initState();
    _nombre = TextEditingController(
      text: context.read<ControladorCreacionPersonaje>().nombre,
    );
  }

  @override
  void dispose() {
    _nombre.dispose();
    super.dispose();
  }

  Future<void> _confirmar() async {
    final ControladorCreacionPersonaje borrador =
        context.read<ControladorCreacionPersonaje>();
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final ColaCelebraciones celebraciones = context.read<ColaCelebraciones>();

    FocusScope.of(context).unfocus();
    if (!borrador.puedeConfirmar) {
      Tacto.ligero(context);
      return;
    }

    final Personaje? creado = await borrador.crear();
    if (!mounted) return;

    if (creado == null) {
      // El héroe ya existía (por ejemplo, un reintento que sí llegó): se
      // recupera la sesión en vez de dejar al usuario atrapado.
      if (borrador.error?.codigo.toUpperCase() == 'CHARACTER_ALREADY_EXISTS') {
        await sesion.refrescarYo();
      }
      return;
    }

    Tacto.medio(context);
    // Primero la celebración (la capa vive por encima del enrutador), después
    // el cambio de fase que abre el Reino.
    celebraciones.encolar(creado.recompensas);
    sesion.anotarPersonaje(creado);
  }

  Future<void> _salirDelReino() async {
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final AteneaPalette paleta = context.paleta;
    final bool? salir = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogo) => AlertDialog(
        backgroundColor: paleta.superficieElevada,
        title: const Text('¿Cierras la sesión?'),
        content: const Text(
          'Tu cuenta queda intacta. Cuando vuelvas, seguirás justo aquí: '
          'creando a tu héroe.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogo).pop(false),
            child: const Text('Seguir aquí'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogo).pop(true),
            child: const Text('Cerrar sesión'),
          ),
        ],
      ),
    );
    if (salir ?? false) await sesion.salir();
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final ControladorCreacionPersonaje borrador =
        context.watch<ControladorCreacionPersonaje>();

    return Scaffold(
      backgroundColor: paleta.fondo,
      appBar: AppBar(
        title: const Text('Crea tu personaje'),
        leading: IconButton(
          icon: const Icon(Icons.logout_rounded),
          tooltip: 'Cerrar sesión',
          onPressed: borrador.guardando ? null : _salirDelReino,
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (BuildContext context, BoxConstraints limites) {
            // El retrato cede altura cuando la pantalla es baja o el tamaño de
            // fuente del sistema crece: nunca empuja al panel fuera.
            final double altoRetrato =
                (limites.maxHeight * 0.30).clamp(128.0, 192.0);
            return Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: Medida.lecturaMax),
                child: Column(
                  children: <Widget>[
                    _Retrato(borrador: borrador, alto: altoRetrato),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(
                        Espacio.md,
                        Espacio.sm,
                        Espacio.md,
                        0,
                      ),
                      child: _CampoNombre(
                        controlador: _nombre,
                        borrador: borrador,
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(
                        Espacio.md,
                        Espacio.sm,
                        Espacio.md,
                        Espacio.xs,
                      ),
                      child: SelectorPestanas(
                        etiquetas: const <String>[
                          'Orden',
                          'Cuerpo',
                          'Figura',
                          'Cabello',
                        ],
                        iconos: const <IconData>[
                          Icons.shield_rounded,
                          Icons.accessibility_new_rounded,
                          Icons.face_retouching_natural_rounded,
                          Icons.content_cut_rounded,
                        ],
                        indice: _pestana,
                        alCambiar: borrador.guardando
                            ? (int _) {}
                            : (int i) => setState(() => _pestana = i),
                      ),
                    ),
                    Expanded(
                      child: borrador.guardando
                          ? const _Forjando()
                          : _PanelOpciones(
                              indice: _pestana,
                              borrador: borrador,
                            ),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ),
      bottomNavigationBar: SafeArea(
        minimum: const EdgeInsets.fromLTRB(
          Espacio.md,
          0,
          Espacio.md,
          Espacio.md,
        ),
        // `heightFactor: 1` hace que la barra mida lo que mide su contenido:
        // un `Center` a secas se quedaría con toda la pantalla.
        child: Align(
          alignment: Alignment.center,
          heightFactor: 1,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: Medida.lecturaMax),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (borrador.error != null) ...<Widget>[
                  AvisoEnLinea(
                    mensaje: borrador.errorNombreServidor ??
                        borrador.error!.mensaje,
                    icono: borrador.error!.codigo == 'sin_conexion'
                        ? Icons.wifi_off_rounded
                        : Icons.error_outline_rounded,
                    textoAccion: 'Reintentar',
                    alTocarAccion: _confirmar,
                  ),
                  const SizedBox(height: Espacio.sm),
                ],
                BotonPrimario(
                  texto: 'Entrar al Reino',
                  subtitulo: borrador.guardando
                      ? null
                      : 'Te esperan tu bolsa de bienvenida y tu kit inicial',
                  icono: Icons.castle_rounded,
                  cargando: borrador.guardando,
                  alTocar: borrador.puedeConfirmar ? _confirmar : null,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Retrato y nombre
// ---------------------------------------------------------------------------

class _Retrato extends StatelessWidget {
  const _Retrato({required this.borrador, required this.alto});

  final ControladorCreacionPersonaje borrador;
  final double alto;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final OrdenVisual visual = borrador.visual;

    return Padding(
      padding: const EdgeInsets.fromLTRB(Espacio.md, Espacio.xs, Espacio.md, 0),
      child: SizedBox(
        height: alto,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: <Widget>[
            Stack(
              alignment: Alignment.bottomRight,
              children: <Widget>[
                // La figura de verdad, no el muñeco vectorial. Desde que se
                // elige entre las seis mirándolas, enseñar aquí otro dibujo
                // haría que la pantalla se contradijera a sí misma: elegirías
                // una cara y verías otra encima.
                SizedBox(
                  height: alto,
                  width: alto,
                  child: AvatarCapas(
                    capas: const <CapaAvatar>[],
                    rasgos: borrador.rasgos,
                    tamano: alto,
                  ),
                ),
                // El dado vive sobre el retrato, junto a lo que cambia.
                Padding(
                  padding: const EdgeInsets.all(Espacio.xxs),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: paleta.superficieElevada,
                      border: Border.all(color: paleta.oro.withValues(alpha: 0.7)),
                    ),
                    child: IconButton(
                      tooltip: 'Aleatorio',
                      iconSize: 22,
                      color: paleta.oro,
                      onPressed: borrador.guardando
                          ? null
                          : () {
                              Tacto.seleccion(context);
                              borrador.aleatorio();
                            },
                      icon: const Icon(
                        Icons.casino_rounded,
                        semanticLabel: 'Rasgos al azar',
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(width: Espacio.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  PildoraElastica(
                    texto: visual.lema,
                    icono: visual.emblema,
                    color: paleta.oro,
                  ),
                  const SizedBox(height: Espacio.xs),
                  Text(
                    borrador.orden.etiqueta,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: context.textos.headlineSmall,
                  ),
                  const SizedBox(height: Espacio.xxs),
                  Flexible(
                    child: Text(
                      visual.descripcion,
                      overflow: TextOverflow.ellipsis,
                      maxLines: 3,
                      style: context.textos.bodyMedium?.copyWith(
                        color: paleta.textoSecundario,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CampoNombre extends StatelessWidget {
  const _CampoNombre({required this.controlador, required this.borrador});

  final TextEditingController controlador;
  final ControladorCreacionPersonaje borrador;

  @override
  Widget build(BuildContext context) {
    final String? aviso =
        borrador.errorNombreServidor ?? _avisoLocal(borrador);
    return TextField(
      controller: controlador,
      enabled: !borrador.guardando,
      textInputAction: TextInputAction.done,
      textCapitalization: TextCapitalization.words,
      maxLength: _maxNombre,
      onChanged: borrador.fijarNombre,
      decoration: InputDecoration(
        labelText: 'Nombre de tu personaje',
        hintText: 'Así te llamará el Reino',
        prefixIcon: const Icon(Icons.badge_outlined),
        errorText: aviso,
        counterText: '',
        helperText: aviso == null
            ? 'Entre $_minNombre y $_maxNombre caracteres.'
            : null,
      ),
    );
  }

  /// Solo se regaña cuando ya se escribió algo: un campo intacto no es un error.
  String? _avisoLocal(ControladorCreacionPersonaje borrador) {
    if (borrador.nombre.isEmpty) return null;
    return borrador.mensajeNombre;
  }
}

/// Mientras el Reino forja al héroe: esqueletos donde estaban las opciones.
class _Forjando extends StatelessWidget {
  const _Forjando();

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        Espacio.md,
        Espacio.md,
        Espacio.lg,
      ),
      children: <Widget>[
        Row(
          children: <Widget>[
            SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(
                strokeWidth: 2.4,
                color: paleta.oro,
              ),
            ),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Text(
                'Forjando tu leyenda…',
                style: context.textos.bodyLarge,
              ),
            ),
          ],
        ),
        const SizedBox(height: Espacio.md),
        const Esqueleto(alto: 56, radio: Redondeo.tarjeta),
        const SizedBox(height: Espacio.xs),
        const Esqueleto(alto: 56, radio: Redondeo.tarjeta),
        const SizedBox(height: Espacio.xs),
        const Esqueleto(alto: 56, radio: Redondeo.tarjeta),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Paneles de opciones
// ---------------------------------------------------------------------------

class _PanelOpciones extends StatelessWidget {
  const _PanelOpciones({required this.indice, required this.borrador});

  final int indice;
  final ControladorCreacionPersonaje borrador;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        0,
        Espacio.md,
        Espacio.lg,
      ),
      children: <Widget>[
        switch (indice) {
          0 => _PanelOrden(borrador: borrador),
          1 => _PanelCuerpo(borrador: borrador),
          2 => _PanelRostro(borrador: borrador),
          _ => _PanelCabello(borrador: borrador),
        },
      ],
    );
  }
}

class _PanelOrden extends StatelessWidget {
  const _PanelOrden({required this.borrador});

  final ControladorCreacionPersonaje borrador;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        const TituloBloque(texto: 'Tu Orden', detalle: 'Solo estilo'),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Icon(
              Icons.info_outline_rounded,
              size: 16,
              color: paleta.textoSecundario,
            ),
            const SizedBox(width: Espacio.xxs + 2),
            Expanded(
              child: Text(
                'Elige por estilo: tu personaje aprende igual que tú. La Orden '
                'solo cambia el atuendo y el título.',
                style: context.textos.bodySmall?.copyWith(
                  color: paleta.textoSecundario,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: Espacio.sm),
        for (final Arquetipo a in CatalogoAvatar.ordenesDisponibles) ...<Widget>[
          _TarjetaOrden(
            arquetipo: a,
            seleccionada: borrador.orden == a,
            alTocar: () => borrador.fijarOrden(a),
          ),
          const SizedBox(height: Espacio.xs),
        ],
        const TituloBloque(texto: 'Próximamente'),
        Wrap(
          spacing: Espacio.xs,
          runSpacing: Espacio.xs,
          children: <Widget>[
            for (final Arquetipo a in CatalogoAvatar.ordenesFuturas)
              PildoraElastica(
                texto: a.etiqueta,
                icono: Icons.lock_outline_rounded,
                color: paleta.textoSecundario,
              ),
          ],
        ),
        const SizedBox(height: Espacio.xs),
        Text(
          'Llegarán en próximas temporadas. Ninguna Orden da ventaja para '
          'aprender.',
          style: context.textos.bodySmall?.copyWith(
            color: paleta.textoSecundario,
          ),
        ),
      ],
    );
  }
}

class _TarjetaOrden extends StatelessWidget {
  const _TarjetaOrden({
    required this.arquetipo,
    required this.seleccionada,
    required this.alTocar,
  });

  final Arquetipo arquetipo;
  final bool seleccionada;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final OrdenVisual visual = CatalogoAvatar.orden(arquetipo);

    return OpcionSeleccionable(
      seleccionada: seleccionada,
      acento: paleta.arcano,
      alTocar: alTocar,
      semantica: '${arquetipo.etiqueta}. ${visual.descripcion}',
      padding: const EdgeInsets.all(Espacio.sm),
      hijo: Row(
        children: <Widget>[
          Container(
            width: Medida.areaTactilMin,
            height: Medida.areaTactilMin,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: visual.principal.withValues(alpha: 0.30),
              border: Border.all(color: visual.acento.withValues(alpha: 0.75)),
            ),
            child: Icon(visual.emblema, size: 22, color: visual.acento),
          ),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  arquetipo.etiqueta,
                  style: context.textos.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  visual.descripcion,
                  style: context.textos.bodySmall?.copyWith(
                    color: paleta.textoSecundario,
                  ),
                ),
              ],
            ),
          ),
          if (seleccionada)
            Icon(Icons.check_circle_rounded, color: paleta.arcano),
        ],
      ),
    );
  }
}

class _PanelCuerpo extends StatelessWidget {
  const _PanelCuerpo({required this.borrador});

  final ControladorCreacionPersonaje borrador;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final RasgosAvatar r = borrador.rasgos;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        const TituloBloque(texto: 'Silueta'),
        Wrap(
          spacing: Espacio.xs,
          runSpacing: Espacio.xs,
          children: <Widget>[
            for (final TipoCuerpo t in CatalogoAvatar.siluetas)
              ChipOpcion(
                texto: t.etiqueta,
                seleccionada: r.tipoCuerpo == t,
                alTocar: () => borrador.fijarRasgos(tipoCuerpo: t),
                semantica: 'Silueta ${t.etiqueta}',
              ),
          ],
        ),
        const TituloBloque(texto: 'Tono de piel'),
        Wrap(
          spacing: Espacio.sm,
          runSpacing: Espacio.sm,
          children: <Widget>[
            for (final OpcionAvatar o in CatalogoAvatar.tonosPiel)
              MuestraColor(
                color: o.color!,
                etiqueta: o.etiqueta,
                seleccionada: r.tonoPiel == o.clave,
                alTocar: () => borrador.fijarRasgos(tonoPiel: o.clave),
              ),
          ],
        ),
        const TituloBloque(texto: 'Cómo te llamamos'),
        Wrap(
          spacing: Espacio.xs,
          runSpacing: Espacio.xs,
          children: <Widget>[
            for (final FormaTrato f in FormaTrato.values)
              ChipOpcion(
                texto: f.etiqueta,
                seleccionada: r.formaTrato == f,
                alTocar: () => borrador.fijarRasgos(formaTrato: f),
                semantica: 'Tratamiento ${f.etiqueta}',
              ),
          ],
        ),
        const SizedBox(height: Espacio.xs),
        Text(
          'Solo cambia cómo te hablan los textos del Reino. Puedes ajustarlo '
          'cuando quieras desde el Vestidor.',
          style: context.textos.bodySmall?.copyWith(
            color: paleta.textoSecundario,
          ),
        ),
      ],
    );
  }
}

class _PanelRostro extends StatelessWidget {
  const _PanelRostro({required this.borrador});

  final ControladorCreacionPersonaje borrador;

  @override
  Widget build(BuildContext context) {
    final RasgosAvatar r = borrador.rasgos;
    final String elegida = Arte.claveDeFigura(
      trato: r.formaTrato,
      cuerpo: r.tipoCuerpo,
      rostro: r.rostro,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        const TituloBloque(texto: 'Tu figura'),
        // Las seis ilustraciones de verdad, no cuatro rostros abstractos.
        //
        // Antes se ofrecían `face_01`..`face_04` y una función los repartía
        // entre las seis figuras junto con el trato y la silueta. El aprendiz
        // no podía saber qué le tocaba: elegía «Rostro 2» y recibía una de seis
        // ilustraciones que no había visto, y dos de los cuatro rostros daban la
        // misma. Ahora se elige mirando.
        //
        // La elección viaja en `rostro`, que es `face_id` en el servidor: una
        // columna de 32 caracteres sin valores tasados. Por eso esto no necesitó
        // migración ni tocar el contrato.
        Wrap(
          spacing: Espacio.sm,
          runSpacing: Espacio.sm,
          children: <Widget>[
            for (final String clave in Arte.personajes)
              _FichaFigura(
                clave: clave,
                seleccionada: elegida == clave,
                alTocar: () => borrador.fijarRasgos(rostro: clave),
              ),
          ],
        ),
      ],
    );
  }
}

/// Una de las seis figuras, para elegirla viéndola.
class _FichaFigura extends StatelessWidget {
  const _FichaFigura({
    required this.clave,
    required this.seleccionada,
    required this.alTocar,
  });

  final String clave;
  final bool seleccionada;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Semantics(
      button: true,
      selected: seleccionada,
      label: 'Figura ${Arte.personajes.indexOf(clave) + 1} de ${Arte.personajes.length}',
      child: InkWell(
        onTap: alTocar,
        borderRadius: BorderRadius.circular(Redondeo.tarjeta),
        child: Container(
          width: 96,
          height: 132,
          decoration: BoxDecoration(
            color: p.superficieElevada,
            borderRadius: BorderRadius.circular(Redondeo.tarjeta),
            border: Border.all(
              color: seleccionada ? p.arcano : p.borde,
              width: seleccionada ? 2 : 1,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          // `alignment: topCenter` y un alto mayor que el ancho: la miniatura
          // enseña la mitad de arriba, que es donde están la cara y el pelo, que
          // es lo que distingue una figura de otra.
          child: Image.asset(
            Arte.personaje(clave),
            alignment: Alignment.topCenter,
            fit: BoxFit.cover,
            filterQuality: FilterQuality.medium,
            errorBuilder: (BuildContext context, Object error, StackTrace? pila) =>
                Icon(Icons.person_rounded, color: p.textoSecundario),
          ),
        ),
      ),
    );
  }
}

class _PanelCabello extends StatelessWidget {
  const _PanelCabello({required this.borrador});

  final ControladorCreacionPersonaje borrador;

  @override
  Widget build(BuildContext context) {
    final RasgosAvatar r = borrador.rasgos;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        const TituloBloque(texto: 'Estilo'),
        Wrap(
          spacing: Espacio.xs,
          runSpacing: Espacio.xs,
          children: <Widget>[
            for (final OpcionAvatar o in CatalogoAvatar.cabellos)
              _FichaRasgo(
                etiqueta: o.etiqueta,
                seleccionada: r.cabello == o.clave,
                alTocar: () => borrador.fijarRasgos(cabello: o.clave),
                rasgos: r.copiarCon(cabello: o.clave),
                orden: borrador.orden,
              ),
          ],
        ),
        const TituloBloque(texto: 'Color'),
        Wrap(
          spacing: Espacio.sm,
          runSpacing: Espacio.sm,
          children: <Widget>[
            for (final OpcionAvatar o in CatalogoAvatar.coloresCabello)
              MuestraColor(
                color: o.color!,
                etiqueta: o.etiqueta,
                seleccionada: r.colorCabello == o.clave,
                alTocar: () => borrador.fijarRasgos(colorCabello: o.clave),
              ),
          ],
        ),
      ],
    );
  }
}

/// Ficha de un rasgo con su propia vista previa del rostro.
class _FichaRasgo extends StatelessWidget {
  const _FichaRasgo({
    required this.etiqueta,
    required this.seleccionada,
    required this.alTocar,
    required this.rasgos,
    required this.orden,
  });

  final String etiqueta;
  final bool seleccionada;
  final VoidCallback alTocar;
  final RasgosAvatar rasgos;
  final Arquetipo orden;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return OpcionSeleccionable(
      seleccionada: seleccionada,
      alTocar: alTocar,
      semantica: etiqueta,
      padding: const EdgeInsets.symmetric(
        horizontal: Espacio.xs,
        vertical: Espacio.xs,
      ),
      hijo: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          // Solo la cabeza: el muñeco se pinta entero y se recorta arriba,
          // para que la muestra sea exactamente lo que se va a ver.
          SizedBox(
            width: 62,
            height: 68,
            child: ClipRRect(
              borderRadius: Redondeo.rChip,
              child: OverflowBox(
                alignment: Alignment.topCenter,
                minWidth: 104,
                maxWidth: 104,
                minHeight: 150,
                maxHeight: 150,
                child: LienzoAvatar(
                  rasgos: rasgos,
                  orden: orden,
                  alto: 150,
                  ancho: 104,
                  conMarco: false,
                  semantica: '',
                ),
              ),
            ),
          ),
          const SizedBox(height: Espacio.xxs),
          SizedBox(
            width: 62,
            child: Text(
              etiqueta,
              textAlign: TextAlign.center,
              overflow: TextOverflow.ellipsis,
              style: context.textos.bodySmall?.copyWith(
                fontWeight: FontWeight.w700,
                color: seleccionada
                    ? paleta.textoPrimario
                    : paleta.textoSecundario,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
